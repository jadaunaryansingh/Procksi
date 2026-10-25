/**
 * Canonical team-UID helpers — drop a copy into each frontend under src/lib/
 * (apps/admin, apps/main, apps/panel, apps/student, apps/mentor).
 *
 * Rule for all new code: the team identity is `team_uid` (uuid). It comes from
 * the API. Do NOT derive it from a string, a slug, or a team number. The team
 * number is display only — use `teamDisplayNumber()` and never compare on it.
 *
 * The old apps/admin/src/lib/teamUtils.js + globalFilters.js number-parsing
 * (teamNumberFromId, findMatchingTeam, cleanUUIDsFromText, resolveTeamNumber)
 * stays ONLY for rendering a label. Any identity/matching use of it is a bug.
 */

const UUID_RE =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

export function isUuid(v) {
  return typeof v === "string" && UUID_RE.test(v.trim());
}

/**
 * Pull the canonical team uid off any API object, checking the known field
 * names in priority order. Returns null if the object has no real uid — callers
 * must treat null as "not a resolvable team", never fall back to a number.
 */
export function teamUidOf(obj) {
  if (!obj || typeof obj !== "object") return isUuid(obj) ? String(obj).trim() : null;
  for (const k of ["team_uid", "teamUid", "uid"]) {
    if (isUuid(obj[k])) return obj[k].trim();
  }
  // some endpoints still send the uid in team_id / teamId during the transition
  for (const k of ["team_id", "teamId"]) {
    if (isUuid(obj[k])) return obj[k].trim();
  }
  return null;
}

/** True when two rows refer to the same team. The only correct team comparison. */
export function sameTeam(a, b) {
  const ua = teamUidOf(a);
  const ub = teamUidOf(b);
  return ua != null && ua === ub;
}

/** Human-facing number. Display only. Never use for lookup, matching, or keys. */
export function teamDisplayNumber(teamRow) {
  if (!teamRow || typeof teamRow !== "object") return null;
  for (const k of ["team_number", "teamNumber", "team_no", "teamNo"]) {
    const n = Number.parseInt(teamRow[k], 10);
    if (Number.isFinite(n) && n > 0 && n < 100000) return n;
  }
  const m = /Team\s*(\d+)/i.exec(String(teamRow.title || teamRow.name || ""));
  return m ? Number.parseInt(m[1], 10) : null;
}

/** Index an array of team rows by uid for O(1) joins. */
export function indexTeamsByUid(teams = []) {
  const map = new Map();
  for (const t of teams) {
    const u = teamUidOf(t);
    if (u) map.set(u, t);
  }
  return map;
}
