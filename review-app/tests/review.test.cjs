'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const R = require('../review.js');
const examples = JSON.parse(fs.readFileSync(path.join(__dirname, '../examples.json'), 'utf8'));
const batch = () => R.parseFile(JSON.stringify(examples)).entries;
test('all original examples validate, retaining 25 calls and temporal order', () => {
  const entries = batch();
  assert.equal(entries.length, 10);
  assert.equal(entries.reduce((n, e) => n + e.example.answers.length, 0), 25);
  assert.deepEqual(entries[0].example.answers.map(a => a.arguments.action), ['unlock', 'cut']);
});
test('supports arrays, wrapped arrays, single records, JSONL and UTF-8 BOM', () => {
  for (const text of [JSON.stringify(examples), JSON.stringify({ examples }), examples.map(e => JSON.stringify(e)).join('\n')]) assert.equal(R.parseFile(text).entries.length, 10);
  assert.equal(R.parseFile(JSON.stringify(examples[0])).entries.length, 1);
  assert.equal(R.parseFile('\uFEFF' + JSON.stringify(examples)).entries.length, 10);
});
test('empty and malformed files have useful errors', () => {
  for (const text of ['', ' ', '[]', '{"examples":[]}', 'null', '[null]', '{broken', '{"query":23}']) assert.throws(() => R.parseFile(text));
});
test('validates tool names, required arguments, argument types and reasoning', () => {
  for (const mutate of [e => { delete e.answers[0].arguments.instrument; }, e => { e.answers[0].name = 'missing'; }, e => { e.answers[0].arguments.target = 42; }, e => { e.reasoning = {}; }, e => { e.tools.push(e.tools[0]); }]) {
    const e = structuredClone(examples[0]); mutate(e);
    assert.throws(() => R.parseFile(JSON.stringify(e)));
  }
});
test('allows explicit no-op examples and optional reasoning', () => {
  const e = { query: 'jfkel;ajioeja', tools: examples[0].tools, answers: [] };
  assert.equal(R.parseFile(JSON.stringify(e)).entries[0].example.reasoning, '');
});
test('rejects oversized inputs and oversized batches', () => {
  assert.throws(() => R.parseFile(' '.repeat(R.MAX_BYTES) + '{}'), /10 MB/);
  assert.throws(() => R.parseFile(JSON.stringify(Array(10001).fill({}))), /10,000/);
});
test('repeated imports deduplicate without replacing existing human labels', () => {
  const entries = R.decide(batch(), 0, 'approve', 'human verified');
  const result = R.mergeEntries(entries, batch());
  assert.equal(result.entries.length, 10);
  assert.equal(result.duplicates, 10);
  assert.equal(result.entries[0].decision, 'approve');
  assert.equal(result.entries[0].reason, 'human verified');
});
test('different object key ordering still deduplicates', () => {
  const e = examples[0];
  const reordered = { answers: e.answers, reasoning: e.reasoning, query: e.query, tools: e.tools };
  assert.equal(R.mergeEntries(batch(), R.parseFile(JSON.stringify(reordered)).entries).added, 0);
});
test('denied examples label the classifier but never become Needle targets', () => {
  let entries = R.decide(batch(), 0, 'approve', 'correct');
  entries = R.decide(entries, 1, 'deny', 'wrong order');
  const needle = R.needle(entries).trim().split('\n').map(JSON.parse);
  const classifier = R.classifier(entries).trim().split('\n').map(JSON.parse);
  assert.equal(needle.length, 1);
  assert.deepEqual(needle[0], examples[0]);
  assert.equal(classifier.length, 2);
  assert.deepEqual(classifier.map(e => e.label), ['approve', 'deny']);
  assert.equal(classifier[1].review_reason, 'wrong order');
  assert.equal(Object.hasOwn(needle[0], 'label'), false);
});
test('changing and clearing decisions updates exports without duplicate rows', () => {
  let entries = R.decide(batch(), 0, 'approve');
  entries = R.decide(entries, 0, 'approve');
  assert.equal(R.needle(entries).trim().split('\n').length, 1);
  entries = R.decide(entries, 0, 'deny');
  assert.equal(R.needle(entries), '');
  assert.equal(JSON.parse(R.classifier(entries)).label, 'deny');
  entries = R.decide(entries, 0, null);
  assert.equal(R.classifier(entries), '');
  assert.equal(R.counts(entries).pending, 10);
});
test('session roundtrip preserves decisions, notes, timestamps, and pending examples', () => {
  const entries = R.decide(batch(), 0, 'deny', 'fix extraction', '2026-11-14T05:00:00.000Z');
  assert.deepEqual(R.parseFile(R.session(entries)).entries, entries);
  const restored = R.mergeEntries(batch(), R.parseFile(R.session(entries)).entries);
  assert.equal(restored.restored, 1);
  assert.deepEqual(restored.entries, entries);
});
test('invalid sessions are rejected rather than silently relabeled', () => {
  const entries = batch();
  entries[0].decision = 'probably';
  assert.throws(() => R.parseFile(R.session(entries)), /Invalid review decision/);
});
test('review and merge operations do not mutate their inputs', () => {
  const entries = batch();
  const snapshot = JSON.stringify(entries);
  const result = R.decide(entries, 0, 'deny');
  R.mergeEntries(entries, result);
  assert.equal(JSON.stringify(entries), snapshot);
  assert.throws(() => R.decide(entries, -1, 'deny'));
});
