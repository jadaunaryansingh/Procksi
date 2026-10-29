# Agentic AI / LLM Analysis File Map

## Scope
This document enumerates **all agentic/LLM-related files** used for GitHub repository analysis, including orchestration, detectors, LLM adapters, and backend integration points. It also shows the data flow between these components.

---

## 1) Orchestration & Pipeline

### Core pipeline
- **src/core/agent.py**
  - **Role:** Main analysis pipeline orchestrator. Defines node functions, builds and runs the pipeline, aggregates results, and returns a final report.
  - **Key functions:**
    - `build_pipeline()` — builds the DAG using `SimpleLangGraph` and executes nodes.
    - `node_*` functions — clone, stack detection, structure analysis, maturity check, commit forensics, quality check, security scan, AI/LLM detection, AI judge, and aggregation.
    - `node_aggregator()` — composes final report with scores, repo tree, AI detection summary, commit data, and security results.

### Graph runner (LangGraph-like)
- **src/orchestrator/langgraph_adapter.py**
  - **Role:** Lightweight DAG executor modeled after LangGraph. Runs nodes in topological order, merges context.
  - **Key classes:** `SimpleLangGraph`, `Node`.

---

## 2) LLM / Agentic Evaluators

### LLM judge (Gemini)
- **src/detectors/product_evaluator.py**
  - **Role:** Calls Gemini for a high-level “product logic” assessment based on a repo summary prompt.
  - **Key function:** `evaluate_product_logic()`
  - **Input:** Repo path → summary text → LLM prompt.
  - **Output:** JSON structure with project name, description, features, tech stack, verdict, and scores.

### Repo summarizer (LLM prompt input)
- **src/utils/repo_summary.py**
  - **Role:** Builds a compressed summary of repo tree and code excerpts for LLM input.
  - **Key function:** `generate_repo_summary()`

---

## 3) AI / Plagiarism Detection

### Heuristic LLM detection
- **src/detectors/llm_detector.py**
  - **Role:** Local heuristic AI-origin score + optional external providers.
  - **Key functions:**
    - `llm_heuristic_score()`
    - `llm_origin_ensemble()`

### External AI detection adapters
- **src/detectors/llm_adapters.py**
  - **Role:** Optional API connectors for Codequiry and Copyleaks AI detection.
  - **Key functions:** `call_codequiry()`, `call_copyleaks()`

### Algorithmic similarity (plagiarism)
- **src/detectors/alg_detector.py**
  - **Role:** Token fingerprint + AST similarity for plagiarism scoring.
  - **Key function:** `algorithmic_similarity()`

---

## 4) Code & Repo Analysis Detectors

- **src/detectors/commit_forensics.py**
  - **Role:** Deep commit analysis (timeline, author stats, suspicious patterns, activity heatmaps).
  - **Key function:** `analyze_commits()`

- **src/detectors/quality_metrics.py**
  - **Role:** Maintainability, complexity, documentation ratios.
  - **Key function:** `analyze_quality()`

- **src/detectors/security_scan.py**
  - **Role:** Secret scanning & security score estimation.
  - **Key function:** `scan_for_secrets()`

- **src/detectors/stack_detector.py**
  - **Role:** Heuristic tech stack detection from files.
  - **Key function:** `detect_tech_stack()`

- **src/detectors/structure_analyzer.py**
  - **Role:** Architecture detection and repo structure scoring.
  - **Key function:** `analyze_structure()`

- **src/detectors/maturity_scanner.py**
  - **Role:** CI/CD + test maturity scoring.
  - **Key function:** `scan_project_maturity()`

---

## 5) Scoring & Report Composition

- **src/core/scoring.py**
  - **Role:** Aggregates risk scores and interprets levels.
  - **Key functions:** `aggregate_scores()`, `interpret_risk()`

- **src/core/report.py**
  - **Role:** Writes JSON/HTML reports.
  - **Key functions:** `write_json_report()`, `generate_simple_html()`

---

## 6) Backend Integration & Persistence

### Analysis runners
- **src/api/backend/background.py**
  - **Role:** Background job entry point for analysis (`run_analysis_job()`), sequential batch runner.

### Analysis API
- **src/api/backend/routers/analysis.py**
  - **Role:** API endpoints to start analysis and query status/results.

### Frontend-compatible API
- **src/api/backend/routers/frontend_api.py**
  - **Role:** Provides `ProjectEvaluation` shape for frontend. Calls `FrontendAdapter`.

### Analytics endpoints
- **src/api/backend/routers/analytics.py**
  - **Role:** Team analytics endpoints that reference project analysis output.

### Data mapping
- **src/api/backend/services/data_mapper.py**
  - **Role:** Maps `agent.py` output → Supabase schema (scores, issues, team members, report_json).

### Frontend adapter
- **src/api/backend/services/frontend_adapter.py**
  - **Role:** Converts DB records/report_json into frontend-ready analytics payloads.

---

## 7) Supporting Utilities Used by Agents

- **src/utils/git_utils.py** — repo cloning, file listing, commit history.
- **src/utils/file_utils.py** — file reading and normalization.
- **src/utils/winnowing.py** and **src/utils/ast_utils.py** — used for similarity/AI detection.
- **src/utils/visualizer.py** — generates dashboard visualizations (used in `agent.py`).

---

## Data Flow (High-Level)

1) **API** → `/api/analyze-repo` (analysis router)
2) **Background** → `run_analysis_job()` → `AnalyzerService.analyze_repository()`
3) **Pipeline** → `core/agent.py` builds DAG and runs detectors
4) **Aggregation** → `node_aggregator()` composes `report_json`
5) **Persistence** → `DataMapper.save_analysis_results()` writes to Supabase
6) **Frontend** → `frontend_api.py` + `FrontendAdapter` produce UI-ready analytics

---

## Implementation Status
- **Orchestration:** Implemented (custom LangGraph-like runner)
- **LLM Judge:** Implemented (Gemini) + repo summary prompt
- **AI Detection:** Implemented (heuristic + optional Codequiry/Copyleaks)
- **Commit Forensics:** Implemented (rich author/time stats)
- **Security/Quality/Structure/Maturity:** Implemented
- **DB Mapping:** Implemented via `data_mapper.py`
- **Frontend Shaping:** Implemented via `frontend_adapter.py`

---

## Next Steps (if needed)
- Ensure analytics endpoints consume `report_json` consistently.
- Add more detailed timeline/heatmap outputs if frontend requires additional fields beyond current `FrontendAdapter` mapping.
