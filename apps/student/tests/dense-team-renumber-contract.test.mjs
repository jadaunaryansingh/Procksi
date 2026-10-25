import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const depsPath = new URL('../../../backend/student-api/app/api/student_deps.py', import.meta.url);
const portalPath = new URL('../../../backend/student-api/app/api/student_portal.py', import.meta.url);

test('student team object carries immutable uid and mutable display number', async () => {
  const source = await readFile(depsPath, 'utf8');
  assert.match(source, /uid=team_data\.get\(["']uid["']\)/);
  assert.match(source, /team_number=display_number/);
  assert.match(source, /display_name\s*=\s*f["']Team \{display_number\}["']/);
});

test('project details read and write GitHub data by immutable team reference', async () => {
  const source = await readFile(portalPath, 'utf8');
  // team.id (the legacy teams.id) is a locally-autoincrementing integer with no
  // relationship to teams_validation.id/uid, so the canonical team_ref/team_uid
  // must be resolved via team_memberships/teams_validation rather than read off
  // that legacy ORM object — getattr(team, "team_number"/"uid", None) always
  // returned None there, since the legacy Team model has neither column.
  assert.match(source, /FROM team_memberships tm/);
  assert.match(source, /JOIN teams_validation tv ON tv\.uid = tm\.team_uid/);
  assert.match(source, /team_ref\s*=\s*canon_row\["team_ref"\]/);
  assert.match(source, /team_uid\s*=\s*canon_row\["team_uid"\]/);
  assert.match(source, /numeric_team_id\s*=\s*canon_row\["team_number"\]\s*or\s*parse_numeric_team_id\(team_ref\)/);
  assert.doesNotMatch(source, /numeric_team_id\s*=\s*getattr\(team, ["']team_number["'], None\)/);
  assert.doesNotMatch(source, /team_uid\s*=\s*getattr\(team, ["']uid["'], None\)/);
  assert.match(source, /github_data \(team_id, team_ref, team_uid, repository_url, raw_json\)/);
  assert.match(source, /github_agent_analysis \(team_id, team_ref, team_uid, repository_url,/);
});
