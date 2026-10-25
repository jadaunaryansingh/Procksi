import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('project details falls back to the latest approved proposal', async () => {
  const source = await readFile(
    new URL('../../../backend/student-api/app/api/student_portal.py', import.meta.url),
    'utf8'
  );

  assert.match(source, /get_latest_approved_proposal_by_team_id/);
  assert.match(source, /project_title.*proposal_title/s);
  assert.match(source, /project_description.*proposal_description/s);
});

test('allocated blueprint prefers fetched project details over stale team placeholders', async () => {
  const source = await readFile(new URL('../src/pages/PreferencesView.jsx', import.meta.url), 'utf8');

  assert.match(source, /title:\s*projectDetails\.project_title\s*\|\|\s*team\.project_title/);
  assert.match(source, /description:\s*projectDetails\.description\s*\|\|\s*team\.description/);
});
