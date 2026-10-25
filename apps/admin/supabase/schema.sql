-- Run this in Supabase SQL Editor before running the import script.

create table if not exists public.semester_config (
    id text primary key,
    year text not null,
    semester_type text not null,
    academic_level integer,
    semester_number integer,
    branch text,
    team_size_min integer,
    team_size_max integer,
    number_of_presentations integer,
    proposal_weight integer,
    mid_weight integer,
    final_weight integer,
    is_active boolean default false,
    is_locked boolean default false,
    results_published boolean default false,
    evaluation_parameters jsonb default '[]'::jsonb
);

create table if not exists public.students (
    id text primary key,
    name text not null,
    email text,
    year integer,
    branch text,
    section text,
    status text default 'Active'
);

create table if not exists public.proposals (
    id text primary key,
    "teamId" text not null,
    title text not null,
    "aiScore" integer,
    "aiRationale" text,
    status text default 'Pending',
    "submittedDate" text
);

create table if not exists public.teams_validation (
    id text primary key,
    title text not null,
    description text,
    leader text,
    domain text,
    mentor text,
    "memberCount" integer default 0,
    "validationStatus" text default 'Pending',
    members jsonb default '[]'::jsonb
);

create table if not exists public.unassigned_students (
    id text primary key,
    name text not null,
    roll text,
    branch text
);

create table if not exists public.mentor_allocations (
    id text primary key,
    title text not null,
    domain text,
    "aiRecommended" text,
    "assignedMentor" jsonb default '[]'::jsonb
);

create table if not exists public.mentors (
    id text primary key,
    name text not null unique,
    email text,
    domain text,
    load integer default 0,
    "maxLoad" integer default 5,
    color text default 'indigo',
    teams integer default 0
);

create table if not exists public.panels (
    id text primary key,
    name text not null unique,
    description text,
    members jsonb default '[]'::jsonb,
    teams integer default 0
);

create table if not exists public.schedule_slots (
    id bigint generated always as identity primary key,
    date text,
    time text,
    team text,
    panel text,
    room text,
    capacity integer,
    "meetLink" text,
    -- Google Calendar event backing "meetLink". The event is created on the
    -- assigned panel's own calendar, so that panel is the Google Meet host.
    meet_event_id text,
    meet_organizer_email text
);
alter table public.schedule_slots add column if not exists meet_event_id text;
alter table public.schedule_slots add column if not exists meet_organizer_email text;

create table if not exists public.evaluation_queue (
    id text primary key,
    team text,
    type text,
    evaluator text,
    "timeStr" text,
    status text
);

create table if not exists public.evaluation_feed (
    id text primary key,
    team text,
    evaluator text,
    score integer,
    "timeAgo" text
);

create table if not exists public.project_locked_ps (
    id text primary key,
    title text,
    "lockedBy" text,
    date text
);

create table if not exists public.project_unallocated_students (
    id text primary key,
    name text,
    reason text,
    "pastTeam" text
);

create table if not exists public.project_override_logs (
    id text primary key,
    admin text,
    action text,
    date text,
    time text
);

create table if not exists public.governance_audit (
    id bigint generated always as identity primary key,
    "user" text,
    action text,
    time text,
    severity text
);

create table if not exists public.sub_admins (
    id bigint generated always as identity primary key,
    name text,
    role text,
    "proposalsReviewed" integer,
    "totalProposals" integer,
    status text
);

create table if not exists public.absent_students (
    id text primary key,
    name text,
    roll text,
    team text,
    reason text,
    status text,
    semester_id text
);

create table if not exists public.makeup_slots (
    id bigint generated always as identity primary key,
    date text,
    time text,
    panel text,
    room text,
    capacity integer,
    enrolled integer
);

create table if not exists public.communication_history (
    id bigint generated always as identity primary key,
    type text,
    recipients text,
    subject text,
    body text,
    date text,
    time text,
    status text
);

create table if not exists public.communication_templates (
    id bigint generated always as identity primary key,
    title text,
    subject text,
    body text
);

create table if not exists public.results (
    team text primary key,
    title text,
    domain text,
    branch text,
    "proposalMarks" integer,
    "midMarks" integer,
    "finalMarks" integer,
    "totalScore" integer
);

alter table public.students enable row level security;
alter table public.proposals enable row level security;
alter table public.teams_validation enable row level security;
alter table public.unassigned_students enable row level security;
alter table public.mentor_allocations enable row level security;
alter table public.mentors enable row level security;
alter table public.panels enable row level security;
alter table public.schedule_slots enable row level security;
alter table public.evaluation_queue enable row level security;
alter table public.evaluation_feed enable row level security;
alter table public.project_locked_ps enable row level security;
alter table public.project_unallocated_students enable row level security;
alter table public.project_override_logs enable row level security;
alter table public.governance_audit enable row level security;
alter table public.sub_admins enable row level security;
alter table public.absent_students enable row level security;
alter table public.makeup_slots enable row level security;
alter table public.communication_history enable row level security;
alter table public.communication_templates enable row level security;
alter table public.results enable row level security;
alter table public.semester_config enable row level security;
drop policy if exists "auth users read students" on public.students;
drop policy if exists "auth users write students" on public.students;
create policy "auth users read students" on public.students for select to authenticated using (true);
create policy "auth users write students" on public.students for all to authenticated using (true) with check (true);

drop policy if exists "auth full access proposals" on public.proposals;
create policy "auth full access proposals" on public.proposals for all to authenticated using (true) with check (true);

drop policy if exists "auth full access teams_validation" on public.teams_validation;
create policy "auth full access teams_validation" on public.teams_validation for all to authenticated using (true) with check (true);

drop policy if exists "auth full access unassigned_students" on public.unassigned_students;
create policy "auth full access unassigned_students" on public.unassigned_students for all to authenticated using (true) with check (true);

drop policy if exists "auth full access mentor_allocations" on public.mentor_allocations;
create policy "auth full access mentor_allocations" on public.mentor_allocations for all to authenticated using (true) with check (true);

drop policy if exists "auth full access mentors" on public.mentors;
create policy "auth full access mentors" on public.mentors for all to authenticated using (true) with check (true);

drop policy if exists "auth full access panels" on public.panels;
create policy "auth full access panels" on public.panels for all to authenticated using (true) with check (true);

drop policy if exists "auth full access schedule_slots" on public.schedule_slots;
create policy "auth full access schedule_slots" on public.schedule_slots for all to authenticated using (true) with check (true);

drop policy if exists "auth full access evaluation_queue" on public.evaluation_queue;
create policy "auth full access evaluation_queue" on public.evaluation_queue for all to authenticated using (true) with check (true);

drop policy if exists "auth full access evaluation_feed" on public.evaluation_feed;
create policy "auth full access evaluation_feed" on public.evaluation_feed for all to authenticated using (true) with check (true);

drop policy if exists "auth full access project_locked_ps" on public.project_locked_ps;
create policy "auth full access project_locked_ps" on public.project_locked_ps for all to authenticated using (true) with check (true);

drop policy if exists "auth full access project_unallocated_students" on public.project_unallocated_students;
create policy "auth full access project_unallocated_students" on public.project_unallocated_students for all to authenticated using (true) with check (true);

drop policy if exists "auth full access project_override_logs" on public.project_override_logs;
create policy "auth full access project_override_logs" on public.project_override_logs for all to authenticated using (true) with check (true);

drop policy if exists "auth full access governance_audit" on public.governance_audit;
create policy "auth full access governance_audit" on public.governance_audit for all to authenticated using (true) with check (true);

drop policy if exists "auth full access sub_admins" on public.sub_admins;
create policy "auth full access sub_admins" on public.sub_admins for all to authenticated using (true) with check (true);

drop policy if exists "auth full access absent_students" on public.absent_students;
create policy "auth full access absent_students" on public.absent_students for all to authenticated using (true) with check (true);

drop policy if exists "auth full access makeup_slots" on public.makeup_slots;
create policy "auth full access makeup_slots" on public.makeup_slots for all to authenticated using (true) with check (true);

drop policy if exists "auth full access communication_history" on public.communication_history;
create policy "auth full access communication_history" on public.communication_history for all to authenticated using (true) with check (true);

drop policy if exists "auth full access communication_templates" on public.communication_templates;
create policy "auth full access communication_templates" on public.communication_templates for all to authenticated using (true) with check (true);

drop policy if exists "auth full access results" on public.results;
create policy "auth full access results" on public.results for all to authenticated using (true) with check (true);

drop policy if exists "auth full access semester_config" on public.semester_config;
create policy "auth full access semester_config" on public.semester_config for all to authenticated using (true) with check (true);
