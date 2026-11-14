(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ZoairkReview = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const MAX_BYTES = 64 * 1024 * 1024;
  const MAX_EXAMPLES = 10000;
  const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  function stable(value) {
    if (Array.isArray(value)) return '[' + value.map(stable).join(',') + ']';
    if (isObject(value)) return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + stable(value[k])).join(',') + '}';
    return JSON.stringify(value);
  }
  function checkValue(value, schema, path) {
    const types = { string: v => typeof v === 'string', object: isObject, array: Array.isArray,
      number: v => typeof v === 'number' && Number.isFinite(v), integer: Number.isInteger,
      boolean: v => typeof v === 'boolean', null: v => v === null };
    if (schema.type && types[schema.type] && !types[schema.type](value)) throw new Error(path + ' must be ' + schema.type + '.');
    if (schema.enum && !schema.enum.some(v => stable(v) === stable(value))) throw new Error(path + ' has an unsupported value.');
    if (isObject(value)) {
      for (const field of schema.required || []) if (!Object.hasOwn(value, field)) throw new Error(path + ' is missing "' + field + '".');
      for (const [key, item] of Object.entries(value)) {
        if (schema.properties && Object.hasOwn(schema.properties, key)) checkValue(item, schema.properties[key], path + '.' + key);
        else if (schema.additionalProperties === false) throw new Error(path + ' has unexpected argument "' + key + '".');
      }
    }
    if (Array.isArray(value) && schema.items) value.forEach((item, i) => checkValue(item, schema.items, path + '[' + i + ']'));
  }
  function validateExample(value, index) {
    const at = 'Example ' + (index + 1);
    if (!isObject(value)) throw new Error(at + ' must be an object.');
    if (typeof value.query !== 'string' || !value.query.trim()) throw new Error(at + ' needs a nonempty query.');
    if (!Array.isArray(value.tools) || !Array.isArray(value.answers)) throw new Error(at + ' needs tools and answers arrays.');
    if (value.reasoning !== undefined && typeof value.reasoning !== 'string') throw new Error(at + ': reasoning must be text.');
    const tools = new Map();
    for (const tool of value.tools) {
      if (!isObject(tool) || typeof tool.name !== 'string' || !tool.name.trim() || !isObject(tool.parameters)) throw new Error(at + ' has an invalid tool schema.');
      if (tools.has(tool.name)) throw new Error(at + ' has duplicate tool names.');
      tools.set(tool.name, tool);
    }
    value.answers.forEach((answer, i) => {
      if (!isObject(answer) || !tools.has(answer.name) || !isObject(answer.arguments)) throw new Error(at + ', call ' + (i + 1) + ': use a declared tool name and an arguments object.');
      checkValue(answer.arguments, tools.get(answer.name).parameters, at + ', call ' + (i + 1));
    });
    return { query: value.query, tools: value.tools, reasoning: value.reasoning || '', answers: value.answers };
  }
  function parseFile(text) {
    if (typeof text !== 'string' || !text.trim()) throw new Error('This file is empty. Choose a JSON file containing examples.');
    if (new TextEncoder().encode(text).length > MAX_BYTES) throw new Error('Use a file smaller than 64 MB.');
    const clean = text.replace(/^\uFEFF/, '').trim();
    let value;
    try { value = JSON.parse(clean); }
    catch {
      try { value = clean.split(/\r?\n/).filter(line => line.trim()).map(line => JSON.parse(line)); }
      catch { throw new Error('Invalid JSON. Use an array of examples, {"examples": [...]}, a single example, or JSONL.'); }
    }
    if (isObject(value) && value.format === 'zoairk-review-session') return parseSession(value);
    const list = Array.isArray(value) ? value : isObject(value) && Array.isArray(value.examples) ? value.examples : [value];
    if (!list.length) throw new Error('This file contains no examples.');
    if (list.length > MAX_EXAMPLES) throw new Error('Use at most 10,000 examples per file.');
    return { entries: list.map((item, i) => ({ example: validateExample(item, i), decision: null, reason: '', reviewedAt: null })), session: false };
  }
  function parseSession(value) {
    if (value.version !== 1 || !Array.isArray(value.entries) || !value.entries.length || value.entries.length > MAX_EXAMPLES) throw new Error('Invalid or unsupported review session.');
    const entries = value.entries.map((entry, i) => {
      if (!isObject(entry) || ![null, 'approve', 'deny'].includes(entry.decision) || typeof entry.reason !== 'string') throw new Error('Invalid review decision in session at example ' + (i + 1) + '.');
      if (entry.reviewedAt !== null && (typeof entry.reviewedAt !== 'string' || !Number.isFinite(Date.parse(entry.reviewedAt)))) throw new Error('Invalid review timestamp at example ' + (i + 1) + '.');
      return { example: validateExample(entry.example, i), decision: entry.decision, reason: entry.reason, reviewedAt: entry.reviewedAt };
    });
    return { entries, session: true };
  }
  function mergeEntries(existing, incoming) {
    const output = existing.map(entry => structuredClone(entry));
    const seen = new Map(output.map((entry, i) => [stable(entry.example), i]));
    let added = 0, restored = 0, duplicates = 0;
    for (const entry of incoming) {
      const key = stable(entry.example);
      if (seen.has(key)) {
        const current = output[seen.get(key)];
        // Existing human decisions win; a session can restore a pending decision.
        if (!current.decision && entry.decision) { Object.assign(current, structuredClone(entry)); restored++; }
        else duplicates++;
      } else { seen.set(key, output.length); output.push(structuredClone(entry)); added++; }
    }
    if (output.length > MAX_EXAMPLES) throw new Error('This workspace would exceed 10,000 examples. Export your session before starting another batch.');
    return { entries: output, added, restored, duplicates };
  }
  function decide(entries, index, decision, reason = '', now = new Date().toISOString()) {
    if (!Number.isInteger(index) || !entries[index] || !['approve', 'deny', null].includes(decision)) throw new Error('Invalid review action.');
    const output = entries.map(entry => structuredClone(entry));
    Object.assign(output[index], { decision, reason: decision ? String(reason).trim() : '', reviewedAt: decision ? now : null });
    return output;
  }
  function counts(entries) {
    return { total: entries.length, approved: entries.filter(e => e.decision === 'approve').length,
      denied: entries.filter(e => e.decision === 'deny').length, pending: entries.filter(e => !e.decision).length };
  }
  const jsonl = rows => rows.length ? rows.map(row => JSON.stringify(row)).join('\n') + '\n' : '';
  function needle(entries) { return jsonl(entries.filter(e => e.decision === 'approve').map(e => e.example)); }
  function classifier(entries) {
    return jsonl(entries.filter(e => e.decision).map(e => ({ ...e.example, label: e.decision, review_reason: e.reason })));
  }
  function session(entries) { return JSON.stringify({ format: 'zoairk-review-session', version: 1, entries }, null, 2) + '\n'; }
  return { MAX_BYTES, parseFile, validateExample, mergeEntries, decide, counts, needle, classifier, session, stable };
});
