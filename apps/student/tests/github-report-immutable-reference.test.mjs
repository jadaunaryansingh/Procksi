import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const portalPath = new URL('../../../backend/student-api/app/api/student_portal.py', import.meta.url);

test('GitHub report endpoint never reads or updates by mutable team number', async () => {
  const source = await readFile(portalPath, 'utf8');
  const start = source.indexOf('@router.get("/team/github")');
  assert.notEqual(start, -1);
  const endpoint = source.slice(start);

  // team.id (the legacy teams.id) is a locally-autoincrementing integer with no
  // relationship to teams_validation.id/uid, so it can never be a valid
  // team_ref/team_uid — the endpoint must resolve the student's team via
  // team_memberships/teams_validation instead, and match github_data/
  // github_agent_analysis on the resulting team_uid.
  assert.doesNotMatch(endpoint, /team_ref\s*=\s*team_id_str/);
  assert.doesNotMatch(endpoint, /team_uid\s*=\s*getattr\(team, ["']uid["'], None\)/);
  assert.match(endpoint, /FROM team_memberships tm/);
  assert.match(endpoint, /JOIN teams_validation tv ON tv\.uid = tm\.team_uid/);
  assert.match(endpoint, /WHERE team_uid = :team_uid/);
  assert.doesNotMatch(endpoint, /WHERE team_id = :nid/);
});
