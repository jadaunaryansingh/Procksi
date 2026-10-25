# Dense Team Renumber Design

## Goal

Renumber the active semester's 193 authoritative teams into the dense display
sequence 1 through 193 without changing team identity, membership, proposal
ownership, repository ownership, or historical evaluation relationships.

## Identity rule

`teams_validation.uid` and `teams_validation.id` remain immutable. Only
`teams_validation.team_number` is a mutable display label. References keyed by
`team_uid`, `team_ref`, or the full team `id` must not change.

## Mapping

Teams are ordered by current `team_number`, then immutable `uid`. The first 183
already occupy 1 through 183. Only these ten labels change:

| Old | New |
| ---: | ---: |
| 958 | 184 |
| 959 | 185 |
| 961 | 186 |
| 962 | 187 |
| 963 | 188 |
| 964 | 189 |
| 965 | 190 |
| 966 | 191 |
| 967 | 192 |
| 968 | 193 |

## Application changes

Admin and student portal display helpers must prefer the explicit
`team_number` returned with a team row. They may parse the immutable ID suffix
only as a compatibility fallback.

Repository reads and writes must resolve ownership through immutable
`team_ref`/`team_uid`. Numeric `github_data.team_id` and
`github_agent_analysis.team_id` remain denormalized display labels and are
updated during renumbering.

## Database transaction

1. Acquire a semester-scoped advisory lock and lock the ten team rows.
2. Recompute and assert the exact approved mapping and free target range.
3. Back up the ten teams, affected GitHub rows, affected analysis rows, and the
   mapping manifest in `renumber_stale_backup_20260808`.
4. Remove the known stale Team 964 analysis for Nikhil's repository after
   backing it up.
5. Update the ten `team_number` values.
6. Update placeholder titles such as `Team 958` to their new display labels.
7. Update denormalized numeric GitHub fields by immutable UID/reference.
8. Update the historical join request's display-only `team_name`; keep its
   immutable `team_id` and `team_uid` unchanged.
9. Commit only if all assertions hold.

## Verification

- Exactly 193 active-semester teams exist with distinct numbers 1 through 193.
- Every membership still points to the same team UID.
- Every proposal retains its original team UID, including the transferred Team
  968 coffee-bean proposal.
- GitHub and analysis rows have numeric labels matching their immutable team.
- No current team label is derived from an immutable ID suffix in the patched
  portal paths.
- Focused regression tests, Python syntax checks, and available frontend builds
  pass before reporting completion.

## Rollback

The backup rows and mapping manifest contain every changed database row. A
rollback restores each row by immutable UID/primary key; immutable IDs are never
rewritten, so memberships and proposal ownership remain stable throughout.
