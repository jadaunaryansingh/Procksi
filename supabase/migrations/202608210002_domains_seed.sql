-- Seed the canonical domains.
--
-- Derived from the observed distribution across problem_statements and
-- teams_validation (189 distinct labels, 1034 mentions). Each row folds in
-- the near-duplicates and one-off variants actually present in that data, so
-- the vocabulary covers real work rather than being invented up front.
--
-- `kind` splits the two things the free text conflated: a mentorable skill
-- versus the application area a project sits in. The signup picker can then
-- offer skills without discarding the application labels the data needs.
--
-- on conflict does nothing: re-running the migration is safe, and it will
-- never overwrite a name an admin has since edited.
insert into public.domains (name, slug, kind, sort_order) values
  ('Artificial Intelligence', 'artificial-intelligence', 'skill', 10),  -- 218 mention(s)
  ('Software Systems', 'software-systems', 'skill', 20),  -- 215 mention(s)
  ('MLOps', 'mlops', 'skill', 30),  -- 202 mention(s)
  ('Cybersecurity', 'cybersecurity', 'skill', 40),  -- 37 mention(s)
  ('DevOps', 'devops', 'skill', 50),  -- 23 mention(s)
  ('Cloud Computing', 'cloud-computing', 'skill', 60),  -- 19 mention(s)
  ('Data Analytics', 'data-analytics', 'skill', 70),  -- 5 mention(s)
  ('Computer Vision', 'computer-vision', 'skill', 80),  -- 4 mention(s)
  ('Natural Language Processing', 'natural-language-processing', 'skill', 90),  -- 2 mention(s)
  ('Web Development', 'web-development', 'skill', 100),  -- 6 mention(s)
  ('Mobile Development', 'mobile-development', 'skill', 110),  -- 0 mention(s)
  ('Autonomous Systems', 'autonomous-systems', 'skill', 120),  -- 13 mention(s)
  ('Robotics', 'robotics', 'skill', 130),  -- 7 mention(s)
  ('Internet of Things', 'internet-of-things', 'skill', 140),  -- 3 mention(s)
  ('Intelligent Automation', 'intelligent-automation', 'skill', 150),  -- 15 mention(s)
  ('Predictive Maintenance', 'predictive-maintenance', 'skill', 160),  -- 9 mention(s)
  ('Sensing & Instrumentation', 'sensing-instrumentation', 'skill', 170),  -- 12 mention(s)
  ('Human-Computer Interaction', 'human-computer-interaction', 'skill', 180),  -- 5 mention(s)
  ('FinTech', 'fintech', 'application', 190),  -- 24 mention(s)
  ('Smart Cities', 'smart-cities', 'application', 200),  -- 15 mention(s)
  ('Smart Buildings', 'smart-buildings', 'application', 210),  -- 17 mention(s)
  ('Industrial & Manufacturing', 'industrial-manufacturing', 'application', 220),  -- 14 mention(s)
  ('AgriTech', 'agritech', 'application', 230),  -- 17 mention(s)
  ('Healthcare', 'healthcare', 'application', 240),  -- 8 mention(s)
  ('Supply Chain & Logistics', 'supply-chain-logistics', 'application', 250),  -- 12 mention(s)
  ('Sustainability & Energy', 'sustainability-energy', 'application', 260),  -- 11 mention(s)
  ('Civil & Infrastructure', 'civil-infrastructure', 'application', 270),  -- 8 mention(s)
  ('Enterprise Operations', 'enterprise-operations', 'application', 280)  -- 7 mention(s)
on conflict (slug) do nothing;
