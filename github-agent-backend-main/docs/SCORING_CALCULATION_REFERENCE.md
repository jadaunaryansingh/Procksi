# Scoring Calculation Reference

This document explains exactly how each score is computed in the current evaluation pipeline.

## 1) Where scoring is finalized

Final per-dimension scores are assembled in `node_aggregator` in `src/core/agent.py`.

The final weighted score written to scorecard output is:

- `TOTAL_SCORE = 0.15*originality + 0.20*implementation + 0.15*engineering + 0.10*security + 0.10*quality + 0.10*test_coverage + 0.05*documentation + 0.05*deployment + 0.10*effort`

This formula is implemented where `score_row["TOTAL_SCORE"]` is computed.

## 2) Raw score sources (before penalties)

## Originality (0-100)

Source:
- LLM forensics output over selected files

Computation:
- For each analyzed file, AI percentage is collected.
- `top_ai = max(ai_percentage_per_file)`
- `originality = max(0, 100 - top_ai)`

Notes:
- This is based on the highest detected AI percentage among analyzed files, not average AI percentage.

## Implementation (0-100)

Source:
- Product evaluator (`src/detectors/product_evaluator.py`) through OpenAI.

Computation flow:
1. Repository summary is generated (`generate_repo_summary`) with sections for frontend/backend/database/core logic.
2. Two part evaluations run (frontend and backend), each returning `implementation_score` + evidence.
3. A synthesis pass returns final `implementation_score` in final judge JSON.
4. Aggregator uses `judge["implementation_score"]` as base implementation score.

Policy adjustment:
- In non-security projects, if `quality_indicators.has_security_measures` is true, evaluator adds `+3` to `implementation_score` (capped 0-100), then sanitizes optional-security mentions.

## Quality (0-100)

Source:
- `src/detectors/quality_metrics.py`

Computation:
- Compute maintainability per language.
- Weighted by file count:
  - `maintainability_index = sum(language_maintainability * language_file_count) / total_files`
- Aggregator uses:
  - `quality = maintainability_index`

## Security (0-100)

Source:
- `src/detectors/security_scan.py` + `src/detectors/score_calculator.py`

Computation:
1. Detect secret leaks and best-practice status.
2. Compute component scores:
   - `secrets_score = max(0, 100 - sum(severity_penalty * confidence))`
   - `practices_score = max(0, 100 - practice_penalties)`
3. Weighted overall:
   - `overall_security = int(0.6*secrets_score + 0.4*practices_score)`
4. Floor:
   - `overall_security = max(20, overall_security)`

Severity penalty defaults:
- critical: 10
- high: 5
- medium: 2
- low: 1

## Effort (0-100)

Source:
- Commit forensics (`total_relevance`, `author_stats`, commit counts)

Base formula:
- `effort_base = min(100, total_relevance * 2)`

Team-size adjustment (applied only to effort base):
- Team size 1: `*1.1`
- Team size 2: `*1.0`
- Team size 3:
  - if commits/person >= 8 OR relevance/person >= 12: `*1.0`
  - else: `*0.9`

Then round to 1 decimal and cap 100.

## Engineering (0-100)

Source:
- `src/detectors/maturity_scanner.py`

Computation:
- DevOps score:
  - Docker: +20
  - Cloud config: +20
  - CI/CD: +20
  - Linting: +10
- Test volume contribution:
  - `test_score = min(30, test_files_count * 6)`
- Base maturity:
  - `maturity_score = min(100, devops_score + test_score)`
- Optional CI/CD deep-analysis bonus:
  - `+ min(10, ci_cd_score // 10)`
- Aggregator uses:
  - `engineering = maturity_score`

## Organization (0-100)

Source:
- `src/detectors/structure_analyzer.py`

Computation:
- Start `org_score = 100`
- Penalties:
  - Flat root clutter (`root_file_count > 15` and `total_folders < 3`): `-40`
  - Excessive nesting (`max_depth > 6`): `-20`
  - Empty/minimal folder structure (`total_folders == 0` and `root_file_count < 5`): force `0`
- Final:
  - `organization = max(0, org_score)`

## Documentation (0-100)

Source:
- `src/detectors/documentation_analyzer.py`

Computation:
- README completeness contributes 40%:
  - `readme_score_weighted = (readme_percentage / 100) * 40`
- API docs contribute up to 30 points:
  - base 20 if any API docs, then +5 per extra doc type (up to 40 in helper), used directly in 0-30 budget path.
- Inline docs contribute up to 30 points via comment ratio heuristic.
- Final:
  - `documentation_score = int(readme_score_weighted + api_docs_score + inline_docs_score)`

## Test Coverage (0-100)

Source:
- `src/detectors/test_coverage_analyzer.py`

Computation:
- Score is heuristic sum of three factors:
1. Test file count (0-30):
   - `min(30, total_test_files * 3)`
2. Test-to-code ratio (0-40):
   - ratio >= 0.3 -> 40
   - ratio >= 0.2 -> 30
   - ratio >= 0.1 -> 20
   - else `min(20, ratio*200)`
3. Framework detection (0-30):
   - +10 if any framework detected
   - +5 per framework up to +20 bonus
- Final:
  - `test_coverage_score = min(100, factor1 + factor2 + factor3)`

## Deployment (0-100)

Source:
- `src/detectors/deployment_verifier.py`

Computation:
- Platform config presence:
  - +10 per platform configured, capped at 30
- URLs in README:
  - +20 if present
- Accessibility:
  - +50 if at least one URL is reachable
- Final:
  - `deployment_score = config_points + url_points + accessibility_points`

Special case:
- If no URLs found, returns partial credit:
  - `30` if any deployment platform configured, else `0`.

## 3) Penalties and what they affect

A combined multiplier is applied to only four dimensions.

Combined multiplier:
- `total_penalty_multiplier = fake_multiplier * quality_multiplier * inactive_penalty * outsourcing_penalty`

Penalty components:
1. Fake commit penalty (`fake_commit_ratio`):
   - <10% -> 1.0
   - 10-30% -> 0.7
   - >30% -> 0.4
2. Quality issue penalty (`quality_issue_ratio`):
   - <40% -> 1.0
   - 40-70% -> 0.85
   - >70% -> 0.7
3. Inactivity penalty:
   - if days since last commit >= 14 -> 0.86 else 1.0
4. Outsourcing penalty from contributor verification severity:
   - minor -> 0.95
   - major -> 0.85
   - critical -> 0.7

Affected dimensions (multiplied and rounded to 1 decimal):
- implementation
- quality
- organization
- effort

Protected dimensions (no penalty multiplier):
- originality
- security
- engineering
- documentation
- test_coverage
- deployment

## 4) Edge-case scoring rules

## Empty or minimal repository

If:
- `total_commits == 0`, or
- `total_commits <= 2` and `total_relevance < 5`

Then forced base scores are:
- originality: 0
- quality: 0
- security: 0
- effort: 0
- implementation: 0
- engineering: 0
- organization: 0
- documentation: 0

(Any missing dimensions in this fallback effectively contribute as 0 in weighted total.)

## Docs-only repository

If both are true:
- `total_commits < 10`
- no code files and only trivial/doc-like files

Then scores are forced to:
- originality: 5
- quality: 5
- security: 5
- effort: 0
- implementation: 5
- engineering: 5
- organization: 5
- documentation: 10

## 5) Relevance score that drives effort

In commit forensics, per-author relevance is:
- `relevance = commits + min(lines_changed, 10000)/100 + 2*active_days`

Total relevance is sum across authors.

Then effort is derived as:
- `effort_base = min(100, total_relevance * 2)` (before team-size and penalties).

## 6) Important mismatch to be aware of (DB total vs scorecard total)

There are currently two total-score formulas in the codebase:

1. `src/core/agent.py` scorecard total (9 dimensions, includes test_coverage and deployment).
2. `src/api/backend/services/data_mapper.py` total (legacy 8-dimension weights):
   - originality 20%
   - quality 15%
   - security 10%
   - effort 10%
   - implementation 25%
   - engineering 10%
   - organization 5%
   - documentation 5%

This can produce different total values across exported scorecard and mapped database records unless harmonized.

## 7) Practical interpretation

When debugging a low final score, inspect in this order:
1. Raw base dimensions (especially implementation, quality, effort, organization)
2. Penalty multipliers and their product
3. Whether empty/minimal or docs-only rule triggered
4. Which total formula consumer is using (scorecard vs DataMapper)

## 8) Files to inspect for each dimension

- Aggregation and final totals: `src/core/agent.py`
- Implementation scoring pipeline: `src/detectors/product_evaluator.py`, `src/utils/repo_summary.py`
- Commit forensics and relevance: `src/detectors/commit_forensics.py`
- Structure/organization: `src/detectors/structure_analyzer.py`
- Engineering maturity: `src/detectors/maturity_scanner.py`
- Security: `src/detectors/security_scan.py`, `src/detectors/score_calculator.py`
- Quality maintainability: `src/detectors/quality_metrics.py`
- Documentation: `src/detectors/documentation_analyzer.py`
- Test coverage: `src/detectors/test_coverage_analyzer.py`
- Deployment: `src/detectors/deployment_verifier.py`
- Database mapping total: `src/api/backend/services/data_mapper.py`
