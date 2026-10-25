create table if not exists public.conversations (
  id          bigint generated always as identity primary key,
  channel     text not null check (channel in ('mentor_student', 'panel_team', 'all')),
  subject     text not null,
  created_by  text not null,
  semester_id text,
  status      text not null default 'open' check (status in ('open', 'closed')),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index if not exists conversations_channel_semester_idx
  on public.conversations(channel, semester_id);

create index if not exists conversations_updated_at_idx
  on public.conversations(updated_at desc);

create table if not exists public.conversation_messages (
  id              bigint generated always as identity primary key,
  conversation_id bigint not null references public.conversations(id) on delete cascade,
  sender_role     text not null check (sender_role in ('admin', 'mentor', 'student', 'panel')),
  sender_id       text not null,
  body            text not null,
  read_by         text[] not null default '{}',
  created_at      timestamptz not null default now()
);

create index if not exists conversation_messages_thread_idx
  on public.conversation_messages(conversation_id, created_at);
