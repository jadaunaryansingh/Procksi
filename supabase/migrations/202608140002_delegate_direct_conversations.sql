-- Direct (per-recipient) conversations for the Delegate dashboard.
-- A conversation with recipient_type IS NULL is a broadcast to a whole
-- channel; one with a recipient_type/id pair is a 1:1 thread with that
-- mentor, team, or panel.
alter table public.conversations
  add column if not exists recipient_type text check (recipient_type in ('mentor', 'team', 'panel')),
  add column if not exists recipient_id text,
  add column if not exists recipient_label text;

create index if not exists conversations_recipient_idx
  on public.conversations(recipient_type, recipient_id)
  where recipient_type is not null;
