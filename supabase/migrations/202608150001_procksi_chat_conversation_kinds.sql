-- Procksi-Chat conversation kinds.
-- A student has four standing threads: with the coordinator, their mentor,
-- their evaluation panel, and their own team. `kind` + `team_id` identify them;
-- the older recipient_type/recipient_id columns remain for admin broadcasts and
-- for direct threads with mentors and panels themselves.
alter table public.conversations
  add column if not exists kind text
    check (kind in ('coordinator', 'mentor', 'panel', 'team')),
  add column if not exists team_id text;

update public.conversations
   set kind = 'coordinator',
       team_id = recipient_id
 where recipient_type = 'team'
   and kind is null;

create unique index if not exists conversations_team_kind_idx
  on public.conversations(team_id, kind)
  where team_id is not null and kind is not null;

create index if not exists conversations_kind_idx
  on public.conversations(kind)
  where kind is not null;
