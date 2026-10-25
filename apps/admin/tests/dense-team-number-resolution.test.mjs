import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('admin team mapping retains mutable display number', async () => {
  const source = await readFile(new URL('../src/pages/TeamValidation.jsx', import.meta.url), 'utf8');
  assert.match(source, /team_number:\s*t\.team_number/);
});

test('teamNumber prefers an explicit row number', async () => {
  const source = await readFile(new URL('../src/lib/teamUtils.js', import.meta.url), 'utf8');
  assert.match(source, /teamNumber\(teamId,\s*row\s*=\s*null\)/);
  assert.match(source, /resolveTeamNumber\(teamId,\s*row\)/);
});
