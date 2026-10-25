-- Custom group threads: one conversation addressed to several named
-- recipients at once (e.g. three mentors and two panels), rather than to a
-- role, a team, or a single person.
--
-- `members` is the authority on who can see a group. The existing
-- recipient_type/recipient_id pair addresses exactly one recipient and
-- `channel` addresses whole roles, so neither can express "these five".
--
-- Each entry is {"type": "mentor"|"panel"|"student"|"team", "id": "...",
-- "label": "..."}. `label` is denormalised on purpose: a group listing must
-- render without joining four directories, and a member later removed from
-- the system should still show as who they were when they were added.

alter table public.conversations
  drop constraint if exists conversations_kind_check;

alter table public.conversations
  add constraint conversations_kind_check
  check (kind = any (array['coordinator', 'mentor', 'panel', 'team', 'group']));

alter table public.conversations
  add column if not exists members jsonb;

-- Membership lookups run on every conversation-list request in four portals,
-- and each one asks "does this array contain me?".
create index if not exists conversations_members_idx
  on public.conversations using gin (members)
  where members is not null;
