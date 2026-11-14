#!/usr/bin/env python3
"""Generate one unreviewed batch through an OpenAI-compatible Ollama endpoint."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import random
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def validate(rows, count, tools, existing):
    if not isinstance(rows, list) or len(rows) != count:
        raise ValueError(f'Expected exactly {count} examples.')
    seen = set(existing)
    for i, row in enumerate(rows, 1):
        if not isinstance(row, dict) or set(row) != {'query', 'reasoning', 'answers'}:
            raise ValueError(f'Example {i}: expected only query, reasoning, answers.')
        if not isinstance(row['query'], str) or not row['query'].strip():
            raise ValueError(f'Example {i}: missing query.')
        key = ' '.join(row['query'].lower().split())
        if key in seen:
            raise ValueError(f'Example {i}: duplicate query.')
        seen.add(key)
        if not isinstance(row['reasoning'], str) or not row['reasoning'].strip():
            raise ValueError(f'Example {i}: missing reasoning.')
        if '<think>' in row['reasoning'] or '</think>' in row['reasoning']:
            raise ValueError(f'Example {i}: reasoning must not contain think wrappers.')
        if not isinstance(row['answers'], list) or not row['answers']:
            raise ValueError(f'Example {i}: expected one or more calls.')
        for answer in row['answers']:
            if not isinstance(answer, dict) or set(answer) != {'name', 'arguments'}:
                raise ValueError(f'Example {i}: invalid call shape.')
            if answer['name'] not in {'enter_command', 'check'}:
                raise ValueError(f'Example {i}: invalid tool.')
            args = answer['arguments']
            if not isinstance(args, dict) or set(args) != {'instrument', 'action', 'target'}:
                raise ValueError(f'Example {i}: invalid arguments.')
            if not all(isinstance(v, str) and v.strip() for v in args.values()):
                raise ValueError(f'Example {i}: arguments must be nonempty strings.')
        for line in row['reasoning'].splitlines():
            # Relationship notation such as A [before] B is not a source-clue line.
            if line.startswith('[') and line.endswith(']') and line[1:-1] not in row['query']:
                raise ValueError(f'Example {i}: temporal clue is absent from query: {line}')
        row['tools'] = tools
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url', default='http://localhost:11434/v1')
    p.add_argument('--model', default='deepseek-v4.1-flash:cloud')
    p.add_argument('--count', type=int, default=20)
    p.add_argument('--reasoning-effort', choices=('low', 'medium', 'high'), default='low')
    p.add_argument('--focus', default='', help='Optional setting/variation emphasis for this batch.')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--raw-output', type=Path, required=True, help='Scratch file outside data/review; preserves rejected responses.')
    p.add_argument('--timeout', type=int, default=600)
    a = p.parse_args()
    if not 1 <= a.count <= 20:
        p.error('Generate 1–20 at a time; review each batch before generating more.')
    if a.output.exists():
        raise SystemExit('Output exists; refusing to replace a previous batch.')
    session = json.loads((ROOT/'data/review/exports/zoairk-review-session.json').read_text())
    approved = [e['example'] for e in session['entries'] if e['decision'] == 'approve']
    tools = approved[-1]['tools']
    # Diverse seed selection; no labels are transferred to generated records.
    rng = random.Random(a.output.stem)
    groups = {}
    for row in approved:
        kind = tuple(sorted({answer['name'] for answer in row['answers']}))
        groups.setdefault(kind, []).append(row)
    selected = []
    for group in groups.values():
        selected.extend(rng.sample(group, min(2, len(group))))
    seeds = [{k: row[k] for k in ('query','reasoning','answers')} for row in selected]
    prior_queries = []
    for batch in sorted((ROOT/'data/review').glob('*-examples.json')):
        prior_queries.extend(r['query'] for r in json.loads(batch.read_text()))
    notes = [{'query': e['example']['query'], 'review_note': e['reason']}
             for e in session['entries'] if e['decision']=='deny' and e['reason']]
    rules = (ROOT/'scripts/generation_rules.md').read_text()
    payload = {'model':a.model, 'stream':False, 'temperature':0.8, 'max_tokens':22000,
               'reasoning_effort':a.reasoning_effort,
               'messages':[{'role':'system','content':rules}, {'role':'user','content':json.dumps({
                   'task':f'Generate exactly {a.count} NEW candidates as a JSON array. They are pending review, not approved.',
                   'batch_tag':a.output.stem, 'variation_focus':a.focus,
                   'tools':tools, 'approved_style_examples':seeds,
                   'previous_denial_notes_to_avoid':notes,
                   'do_not_repeat_queries':prior_queries},ensure_ascii=False)}]}
    a.raw_output.parent.mkdir(parents=True, exist_ok=True)
    headers = {'Content-Type':'application/json'}
    if os.environ.get('OLLAMA_API_KEY'):
        headers['Authorization']='Bearer '+os.environ['OLLAMA_API_KEY']
    request = urllib.request.Request(a.base_url.rstrip('/')+'/chat/completions',
                                    data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(request, timeout=a.timeout) as response:
        result = json.load(response)
    a.raw_output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    choice = result['choices'][0]
    if choice.get('finish_reason') != 'stop':
        raise SystemExit('Generation did not finish normally; raw response saved, no candidate file written.')
    text = choice['message']['content'].strip()
    if text.startswith('```json\n') and text.endswith('```'):
        text=text[len('```json\n'):-3].strip()
    rows=validate(json.loads(text),a.count,tools,{' '.join(q.lower().split()) for q in prior_queries})
    content=json.dumps(rows,ensure_ascii=False,indent=2)+'\n'
    # Check with the same validator the webapp uses, before writing a batch.
    checker="const fs=require('node:fs'); const R=require('./review-app/review.js'); R.parseFile(fs.readFileSync(0,'utf8'));"
    subprocess.run(['node','-e',checker],input=content,text=True,cwd=ROOT,check=True)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f:
        f.write(content)
    meta=ROOT/'data/generation'/ (a.output.stem+'.json')
    meta.parent.mkdir(parents=True,exist_ok=True)
    metadata={'model':a.model,'reasoning_effort':a.reasoning_effort,'created_at':datetime.now(timezone.utc).isoformat(),
              'count':len(rows),'variation_focus':a.focus,'status':'pending_review_at_generation',
              'batch_path':str(a.output.resolve().relative_to(ROOT)),
              'sha256':hashlib.sha256(content.encode()).hexdigest(),
              'rules_sha256':hashlib.sha256(rules.encode()).hexdigest(),
              'usage':result.get('usage'), 'seed_source':'data/review/exports/zoairk-review-session.json'}
    with meta.open('x') as f:
        f.write(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps(metadata,indent=2))


if __name__=='__main__':
    main()
