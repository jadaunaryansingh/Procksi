-- The four standing groups replace user-created ones.
--
-- Membership is derived from role at read time, never stored. That is the
-- whole point: "all mentors, existing and upcoming" cannot be a snapshot,
-- because a mentor appointed next week has to be in the group without anyone
-- editing it. It also disposes of the double-membership problem — a person who
-- is both a mentor and a panel matches the Mentors group through their mentor
-- role and the Panels group through their panel role, and Everyone exactly
-- once. There is no member list in which they could appear twice.
--
-- `group_key` is therefore the entire definition of a group, and the unique
-- index guarantees exactly one row per key however many portals race to read
-- them.

alter table public.conversations
  add column if not exists group_key text
    check (group_key in ('mentors', 'panels', 'teams', 'everyone'));

create unique index if not exists conversations_group_key_idx
  on public.conversations(group_key)
  where group_key is not null;

-- `members` held the explicit recipient list of a user-created group. Nothing
-- creates those any more and no row ever carried a value, so the column would
-- only mislead a future reader into thinking membership is stored.
drop index if exists conversations_members_idx;
alter table public.conversations drop column if exists members;

-- The groups are institution-wide, so semester_id stays NULL: they are not
-- scoped to a cohort and must survive a semester rollover.
insert into public.conversations (channel, subject, created_by, status, kind, group_key, updated_at)
values
  ('all', 'All Mentors', 'system', 'open', 'group', 'mentors',  now()),
  ('all', 'All Panels',  'system', 'open', 'group', 'panels',   now()),
  ('all', 'All Teams',   'system', 'open', 'group', 'teams',    now()),
  ('all', 'Everyone',    'system', 'open', 'group', 'everyone', now())
on conflict do nothing;
