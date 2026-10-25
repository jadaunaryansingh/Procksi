-- Migration: Replace Hardcoded Evaluations with Dynamic Presentation Cycles
-- Table: presentation_cycles
create table if not exists public.presentation_cycles (
    id uuid default gen_random_uuid() primary key,
    semester_id text,
    title text not null,
    type text not null default 'mid',
    description text,
    weightage integer not null default 0,
    deadline timestamptz not null,
    status text not null default 'draft', -- draft, active, closed, frozen
    requires_synopsis boolean not null default false,
    enable_mentor_eval boolean not null default false,
    mentor_max_marks integer not null default 0,
    created_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- Table: presentation_submissions
create table if not exists public.presentation_submissions (
    id uuid default gen_random_uuid() primary key,
    cycle_id uuid not null references public.presentation_cycles (id) on delete cascade,
    team_id text not null,
    student_id text,
    submission_type text not null default 'github',
    file_url text,
    github_url text,
    notes text,
    submitted_at timestamptz not null default now()
);

-- Table: presentation_evaluations
create table if not exists public.presentation_evaluations (
    id uuid default gen_random_uuid() primary key,
    cycle_id uuid not null references public.presentation_cycles (id) on delete cascade,
    team_id text not null,
    evaluator_id text not null,
    evaluator_type text not null default 'mentor', -- mentor, panel
    total_score integer not null,
    remarks text,
    evaluated_at timestamptz not null default now()
);

-- Table: presentation_schedule
create table if not exists public.presentation_schedule (
    id uuid default gen_random_uuid() primary key,
    cycle_id uuid not null references public.presentation_cycles (id) on delete cascade,
    team_id text not null,
    panel_id text,
    slot_datetime timestamptz not null,
    meeting_link text,
    room_number text,
    status text not null default 'scheduled',
    created_at timestamptz not null default now()
);

-- Table: presentation_cycle_audit
create table if not exists public.presentation_cycle_audit (
    id uuid default gen_random_uuid() primary key,
    cycle_id uuid not null references public.presentation_cycles (id) on delete cascade,
    action text not null,
    performed_by text not null,
    metadata jsonb default '{}'::jsonb,
    timestamp timestamptz not null default now()
);

-- Future Ready Tables
create table if not exists public.presentation_rubrics (
    id uuid default gen_random_uuid() primary key,
    cycle_id uuid not null references public.presentation_cycles (id) on delete cascade,
    criterion text not null,
    max_marks integer not null,
    weight integer not null default 1
);

create table if not exists public.presentation_evaluation_scores (
    evaluation_id uuid not null references public.presentation_evaluations (id) on delete cascade,
    rubric_id uuid not null references public.presentation_rubrics (id) on delete cascade,
    awarded_marks integer not null,
    primary key (evaluation_id, rubric_id)
);

-- RLS Policies
alter table public.presentation_cycles enable row level security;
alter table public.presentation_submissions enable row level security;
alter table public.presentation_evaluations enable row level security;
alter table public.presentation_schedule enable row level security;
alter table public.presentation_cycle_audit enable row level security;
alter table public.presentation_rubrics enable row level security;
alter table public.presentation_evaluation_scores enable row level security;

-- Drop policies if exist to ensure idempotency
drop policy if exists "auth full access presentation_cycles" on public.presentation_cycles;
drop policy if exists "auth full access presentation_submissions" on public.presentation_submissions;
drop policy if exists "auth full access presentation_evaluations" on public.presentation_evaluations;
drop policy if exists "auth full access presentation_schedule" on public.presentation_schedule;
drop policy if exists "auth full access presentation_cycle_audit" on public.presentation_cycle_audit;
drop policy if exists "auth full access presentation_rubrics" on public.presentation_rubrics;
drop policy if exists "auth full access presentation_evaluation_scores" on public.presentation_evaluation_scores;

-- Create policies (for now, authenticated users have full access, similar to existing setup)
create policy "auth full access presentation_cycles" on public.presentation_cycles for all to authenticated using (true) with check (true);
create policy "auth full access presentation_submissions" on public.presentation_submissions for all to authenticated using (true) with check (true);
create policy "auth full access presentation_evaluations" on public.presentation_evaluations for all to authenticated using (true) with check (true);
create policy "auth full access presentation_schedule" on public.presentation_schedule for all to authenticated using (true) with check (true);
create policy "auth full access presentation_cycle_audit" on public.presentation_cycle_audit for all to authenticated using (true) with check (true);
create policy "auth full access presentation_rubrics" on public.presentation_rubrics for all to authenticated using (true) with check (true);
create policy "auth full access presentation_evaluation_scores" on public.presentation_evaluation_scores for all to authenticated using (true) with check (true);
