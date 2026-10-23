import test from 'node:test';
import assert from 'node:assert/strict';
import { blockToDraft, duplicateSlideBody } from '../client/src/pages/deck/blocks.js';

test('copies visible content through the existing block conversion without source identity', () => {
  const saved = { id: 'source', status: 'approved', revision: 7, outline_id: 'outline',
    layout: 'chart', title: 'Saved', subtitle: 'Context', notes: 'Speaker notes', image_prompt: '', sources: [12],
    blocks: [{ type: 'chart', chart: 'bar', categories: ['Q1'], series: [{ name: 'Revenue', values: [2] }] },
      { type: 'image', asset_id: 'figure', caption: 'Registered figure' }] };
  const before = structuredClone(saved);
  const draft = { ...saved, blocks: saved.blocks.map(blockToDraft), title: 'Visible unsaved title' };
  draft.blocks[0].series[0].values[0] = '3,5';
  const body = duplicateSlideBody(saved.id, draft, key => key);
  assert.deepEqual(Object.keys(body).sort(), ['after_id', 'blocks', 'image_prompt', 'layout', 'notes', 'sources', 'subtitle', 'title']);
  assert.equal(body.after_id, saved.id);
  assert.equal(body.title, 'Visible unsaved title');
  assert.equal(body.blocks[0].series[0].values[0], 3.5);
  assert.equal(body.blocks[1].asset_id, 'figure');
  assert.deepEqual(body.sources, [12]);
  body.sources.push(13);
  assert.deepEqual(draft.sources, [12]);
  assert.deepEqual(saved, before);
});

test('invalid partial chart input keeps the visible draft available for correction', () => {
  const draft = { layout: 'chart', title: 'Pending edit', subtitle: '', notes: 'Keep my notes', image_prompt: '', sources: [],
    blocks: [{ type: 'chart', chart: 'bar', categories: ['Q1'], series: [{ name: 'Revenue', values: ['-'] }] }] };
  const before = structuredClone(draft);
  assert.throws(() => duplicateSlideBody('source', draft, key => key), /chart_invalid_values/);
  assert.deepEqual(draft, before);
});
