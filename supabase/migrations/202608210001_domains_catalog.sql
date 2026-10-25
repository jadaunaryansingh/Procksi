-- A curated vocabulary of mentoring domains.
--
-- Until now there was no such list. The mentor signup picker derived its
-- options from teams_validation.domain — free text written by two unconstrained
-- writers: the `Domain:` line of an uploaded problem-statement document, and an
-- OpenAI enrichment step that invents a label per project. Neither validates
-- against anything, so 154 problem statements produced 145 distinct "domains",
-- 75% of them appearing exactly once. The picker offered project descriptions
-- ("Construction Quality Assurance", "Bulk Material Handling") as selectable
-- expertise, alongside near-duplicates the parser cannot merge — AgTech and
-- Agritech, Bio-Tech and BioTech.
--
-- This table is the vocabulary those writers can be validated against. It
-- deliberately does NOT normalise the existing free-text columns: teams,
-- problem statements and mentors keep their stored strings, and nothing here
-- rewrites them. The table exists so that new values can be constrained and so
-- the picker stops depending on which projects happen to be allocated.
create table if not exists public.domains (
  id          uuid primary key default gen_random_uuid(),
  -- Display label, e.g. 'Artificial Intelligence'. May be re-worded later.
  name        text not null,
  -- Stable machine key. References match on this, never on `name`, so renaming
  -- a domain for display does not orphan anything that points at it.
  slug        text not null,
  -- Separates a mentorable skill ('Computer Vision') from the application area
  -- a project sits in ('AgriTech'). Mentors realistically claim the first;
  -- projects are described by the second. One table serves both, and a picker
  -- filters by kind rather than needing a second catalogue.
  kind        text not null default 'skill'
                check (kind in ('skill', 'application')),
  -- Deactivate rather than delete. A domain a mentor has already claimed must
  -- not vanish from history — the same hazard as deleting a panel row out from
  -- under a registered account.
  is_active   boolean not null default true,
  sort_order  integer not null default 0,
  created_at  timestamptz not null default now()
);

create unique index if not exists domains_slug_idx
  on public.domains(slug);

-- Case-insensitive uniqueness on the display label is the guard that the free
-- text never had: it makes 'AgTech' and 'agtech' the same row by construction.
create unique index if not exists domains_name_lower_idx
  on public.domains(lower(name));

-- Matches every other table in this schema: RLS on with no permissive policy,
-- so the service-key backends read it and anon clients get [] rather than data.
alter table public.domains enable row level security;
