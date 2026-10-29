"""
Analyzer Service
Wrapper for agent.py pipeline with progress tracking
"""
import os
import sys
import copy
from uuid import UUID
from typing import Dict, Any
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.agent import build_pipeline
from src.api.backend.utils.progress_tracker import ProgressTracker
from src.api.backend.services.data_mapper import DataMapper
from src.api.backend.crud import TeamCRUD



class AnalyzerService:
    """Service to run repository analysis with progress tracking"""

    @staticmethod
    def _format_repo_feedback_block(repo_url: str | None, report: Dict[str, Any]) -> str | None:
        """Format a repo-level feedback block for merged team reports."""
        if not isinstance(report, dict):
            return None

        parts: list[str] = []
        label = repo_url or report.get("repo_url") or "Repository"

        for title, key in (
            ("Strengths", "positive_feedback"),
            ("Improvements", "constructive_feedback"),
            ("Recommendation", "overall_recommendation"),
            ("Verdict reasoning", "verdict_reasoning"),
        ):
            value = report.get(key)
            if not value:
                continue
            text = str(value).strip()
            if not text:
                continue
            parts.append(f"{title}: {text}")

        if not parts:
            return None

        return f"{label}\n" + "\n".join(parts)

    @staticmethod
    def _merge_text_list(values: list[Any]) -> list[str]:
        """Merge list values while preserving order and removing duplicates."""
        merged: list[str] = []
        seen: set[str] = set()

        for value in values:
            if isinstance(value, list):
                items = value
            elif value is None:
                items = []
            else:
                items = [value]

            for item in items:
                text = str(item).strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                merged.append(text)

        return merged

    @staticmethod
    def _merge_repo_feedback(reports: list[Dict[str, Any]], repo_urls: list[str]) -> Dict[str, Any]:
        """Merge repo-level narrative feedback into a single team-level summary."""
        labeled_blocks = []
        positive_sections = []
        improvement_sections = []
        recommendation_sections = []
        verdict_sections = []
        reasoning_sections = []
        feature_analysis = []
        suggested_features = []

        # Patterns that suggest missing components, which might be irrelevant in multi-repo context
        is_multi_repo = len(reports) > 1
        ignore_patterns = [
            "missing a frontend", "no frontend detected", "missing frontend",
            "missing a backend", "no backend detected", "missing backend",
            "only contains frontend", "only contains backend",
            "the project seems to be missing", "incomplete without a",
            "no clear entry point", "does not look like a full app",
            "missing db integration", "missing database",
            "limited to one side of the stack"
        ]

        def filter_generic_missing(text: str | None) -> str | None:
            if not text or not is_multi_repo:
                return text
            
            # Split by common sentence/point delimiters
            import re
            parts = re.split(r'([.!?;\n])', text)
            
            filtered_parts = []
            # parts will look like ['sentence', '.', 'next', '!', ...]
            for i in range(0, len(parts), 2):
                content = parts[i]
                delimiter = parts[i+1] if i+1 < len(parts) else ""
                
                if any(p.lower() in content.lower() for p in ignore_patterns):
                    continue
                
                filtered_parts.append(content + delimiter)
            
            result = "".join(filtered_parts).strip()
            # Clean up double punctuation that might result from filtering
            result = re.sub(r'\s+([.!?;,])', r'\1', result)
            return result if result else None

        for index, report in enumerate(reports):
            repo_url = repo_urls[index] if index < len(repo_urls) else report.get("repo_url")
            
            # Create a sanitized version of the report for the summary block
            sanitized_report = copy.deepcopy(report)
            for key in ["positive_feedback", "constructive_feedback", "overall_recommendation", "verdict_reasoning"]:
                sanitized_report[key] = filter_generic_missing(report.get(key))

            block = AnalyzerService._format_repo_feedback_block(repo_url, sanitized_report)
            if block:
                labeled_blocks.append(block)

            label_prefix = f"[{repo_url or report.get('repo_url') or 'Repository'}]"
            
            for key, target_list in [
                ("positive_feedback", positive_sections),
                ("constructive_feedback", improvement_sections),
                ("overall_recommendation", recommendation_sections),
                ("verdict_reasoning", reasoning_sections),
            ]:
                val = filter_generic_missing(report.get(key))
                if val:
                    target_list.append(f"{label_prefix} {val}")

            if report.get("verdict"):
                verdict_sections.append(f"{label_prefix} {report.get('verdict')}")

            if isinstance(report.get("feature_analysis"), list):
                feature_analysis.extend(report.get("feature_analysis") or [])
            if isinstance(report.get("suggested_features"), list):
                suggested_features.extend(report.get("suggested_features") or [])

        return {
            "repo_feedback_summary": "\n\n".join(labeled_blocks) if labeled_blocks else None,
            "positive_feedback": "\n\n".join(positive_sections) if positive_sections else None,
            "constructive_feedback": "\n\n".join(improvement_sections) if improvement_sections else None,
            "overall_recommendation": "\n\n".join(recommendation_sections) if recommendation_sections else None,
            "verdict_reasoning": "\n\n".join(reasoning_sections) if reasoning_sections else None,
            "repo_verdicts": verdict_sections,
            "feature_analysis": AnalyzerService._merge_text_list(feature_analysis),
            "suggested_features": suggested_features,
        }

    @staticmethod
    def _normalize_text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _extract_project_statement(metadata: Dict[str, Any]) -> str | None:
        """Extract project context from known metadata variants."""
        if not isinstance(metadata, dict):
            return None

        ingestion = metadata.get("ingestion") or {}
        candidates = [
            ingestion.get("project_statement"),
            ingestion.get("problem_statement"),
            ingestion.get("project_description"),
            metadata.get("project_statement"),
            metadata.get("problem_statement"),
            metadata.get("project_description"),
            metadata.get("project_name"),
            metadata.get("name"),
            ingestion.get("project_name"),
            ingestion.get("name"),
        ]

        for candidate in candidates:
            normalized = AnalyzerService._normalize_text(candidate)
            if normalized:
                return normalized
        return None

    @staticmethod
    def _fetch_github_languages(repo_url: str, token: str) -> Dict[str, float]:
        """Fetch language breakdown from GitHub API"""
        import httpx
        
        try:
            # Extract owner/repo
            cleaned = repo_url.rstrip("/").replace(".git", "")
            parts = cleaned.split("/")
            if len(parts) < 2:
                return {}
            repo_path = f"{parts[-2]}/{parts[-1]}"
            
            api_url = f"https://api.github.com/repos/{repo_path}/languages"
            
            with httpx.Client() as client:
                response = client.get(
                    api_url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github.v3+json"
                    },
                    timeout=10.0
                )
                
                if response.status_code != 200:
                    print(f"      ⚠️  GitHub API Lookup Failed: {response.status_code}")
                    return {}
                
                data = response.json()
                total_bytes = sum(data.values())
                
                if total_bytes == 0:
                    return {}
                    
                breakdown = {}
                for lang, bytes_count in data.items():
                    percentage = round((bytes_count / total_bytes) * 100, 2)
                    breakdown[lang] = percentage
                    
                return breakdown
                
        except Exception as e:
            print(f"      ⚠️  Language fetch error: {e}")
            return {}

    @staticmethod
    def _normalize_repo_urls(repo_urls: list[str] | None, primary_repo_url: str | None = None) -> list[str]:
        """Normalize repository URLs while preserving order and removing duplicates. Handles comma-separated values."""
        normalized_urls: list[str] = []
        seen: set[str] = set()

        def add_url(value: str | None) -> None:
            if value is None:
                return
            
            # Handle comma-separated values within a single string
            for part in str(value).split(','):
                cleaned = part.strip()
                if not cleaned:
                    continue
                if 'github.com' not in cleaned.lower():
                    raise ValueError(f'Only GitHub repositories are supported, found: {cleaned}')
                if cleaned in seen:
                    continue
                seen.add(cleaned)
                normalized_urls.append(cleaned)

        add_url(primary_repo_url)

        if repo_urls:
            for repo_url in repo_urls:
                add_url(repo_url)

        return normalized_urls


    @staticmethod
    def _get_team_repo_urls(team_id: UUID, fallback_repo_url: str | None = None) -> list[str]:
        """Fetch the primary and additional repository URLs associated with a team."""
        try:
            from src.api.backend.database import get_supabase_admin_client
            supabase = get_supabase_admin_client()
            team_result = supabase.table("teams").select("repo_url, metadata").eq("id", str(team_id)).execute()
            if not team_result.data:
                return AnalyzerService._normalize_repo_urls([fallback_repo_url] if fallback_repo_url else [])

            team_row = team_result.data[0] or {}
            metadata = team_row.get("metadata") or {}
            if not isinstance(metadata, dict):
                metadata = {}

            repo_urls = []
            if team_row.get("repo_url"):
                repo_urls.append(team_row.get("repo_url"))

            metadata_repo_urls = metadata.get("repo_urls") or metadata.get("additional_repo_urls") or []
            if isinstance(metadata_repo_urls, list):
                repo_urls.extend(metadata_repo_urls)

            if not repo_urls and fallback_repo_url:
                repo_urls.append(fallback_repo_url)

            return AnalyzerService._normalize_repo_urls(repo_urls)
        except Exception:
            return AnalyzerService._normalize_repo_urls([fallback_repo_url] if fallback_repo_url else [])

    @staticmethod
    def _merge_repository_reports(reports: list[Dict[str, Any]], repo_urls: list[str]) -> Dict[str, Any]:
        """Merge multiple repository reports into a single team report."""
        if not reports:
            return {}

        if len(reports) == 1:
            merged_report = copy.deepcopy(reports[0])
            merged_report["related_repositories"] = repo_urls
            merged_report["repo_analysis_breakdown"] = [
                {
                    "repo_url": repo_urls[0] if repo_urls else merged_report.get("repo_url"),
                    "scores": merged_report.get("scores", {}),
                    "total_score": merged_report.get("final_scores", {}).get("total_score") or merged_report.get("total_score"),
                }
            ]
            return merged_report

        score_keys = [
            "originality", "quality", "security", "effort",
            "implementation", "engineering", "organization", "documentation",
        ]

        weights: list[float] = []
        normalized_reports: list[Dict[str, Any]] = []
        for report in reports:
            normalized_report = report if isinstance(report, dict) else {}
            normalized_reports.append(normalized_report)
            weight = float(normalized_report.get("lines_of_code") or 0)
            if weight <= 0:
                weight = float(normalized_report.get("file_count") or 0)
            if weight <= 0:
                weight = 1.0
            weights.append(weight)

        merged_scores: Dict[str, float] = {}
        for score_key in score_keys:
            weighted_sum = 0.0
            valid_weight_total = 0.0
            for report, weight in zip(normalized_reports, weights):
                score_block = report.get("scores", {}) if isinstance(report.get("scores"), dict) else {}
                
                if score_key not in score_block or score_block.get(score_key) is None:
                    continue
                
                try:
                    numeric_score = float(score_block.get(score_key))
                except (TypeError, ValueError):
                    continue
                    
                weighted_sum += numeric_score * weight
                valid_weight_total += weight
                
            if valid_weight_total > 0:
                merged_scores[score_key] = round(weighted_sum / valid_weight_total, 1)
            else:
                merged_scores[score_key] = 0.0

        merged_report = copy.deepcopy(normalized_reports[0])
        merged_report["scores"] = merged_scores
        merged_report.setdefault("final_scores", {})
        merged_report["final_scores"]["total_score"] = DataMapper.calculate_total_score({
            f"{key}_score": value for key, value in merged_scores.items()
        })
        merged_report["repo_url"] = repo_urls[0] if repo_urls else merged_report.get("repo_url")
        merged_report["related_repositories"] = repo_urls

        merged_feedback = AnalyzerService._merge_repo_feedback(normalized_reports, repo_urls)
        for key, value in merged_feedback.items():
            if value is not None:
                merged_report[key] = value

        merged_report["commit_count"] = sum(int(report.get("commit_count") or 0) for report in normalized_reports)
        merged_report["file_count"] = sum(int(report.get("file_count") or 0) for report in normalized_reports)
        merged_report["lines_of_code"] = sum(int(report.get("lines_of_code") or 0) for report in normalized_reports)

        merged_team: Dict[str, Any] = {}
        for report in normalized_reports:
            team_block = report.get("team", {})
            if not isinstance(team_block, dict):
                continue
            for author, stats in team_block.items():
                if isinstance(stats, dict):
                    commits = int(stats.get("commits") or stats.get("commit_count") or 0)
                else:
                    try:
                        commits = int(stats or 0)
                    except (TypeError, ValueError):
                        commits = 0
                existing = merged_team.get(author, {"commits": 0})
                existing["commits"] = int(existing.get("commits", 0) or 0) + commits
                merged_team[author] = existing
        merged_report["team"] = merged_team
        merged_report["team_members"] = [
            {"name": author, "commits": stats.get("commits", 0), "contribution_pct": None}
            for author, stats in merged_team.items()
        ]

        merged_author_stats: Dict[str, Dict[str, Any]] = {}
        for report in normalized_reports:
            forensics = report.get("forensics", {})
            author_stats = forensics.get("author_stats", {}) if isinstance(forensics, dict) else {}
            if isinstance(author_stats, dict):
                items = author_stats.items()
            elif isinstance(author_stats, list):
                items = ((item.get("author") or item.get("name") or f"author-{index}", item) for index, item in enumerate(author_stats) if isinstance(item, dict))
            else:
                items = []

            for author, stats in items:
                if not author:
                    continue
                current = merged_author_stats.setdefault(str(author), {"commits": 0})
                if isinstance(stats, dict):
                    current["commits"] = int(current.get("commits", 0) or 0) + int(stats.get("commits") or stats.get("commit_count") or 0)
                elif isinstance(stats, int):
                    current["commits"] = int(current.get("commits", 0) or 0) + int(stats)

        merged_report.setdefault("forensics", {})
        merged_report["forensics"]["author_stats"] = merged_author_stats

        merged_report["issues"] = [
            issue for report in normalized_reports
            for issue in (report.get("issues", []) if isinstance(report.get("issues", []), list) else [])
        ]
        merged_report["repo_analysis_breakdown"] = [
            {
                "repo_url": repo_urls[index] if index < len(repo_urls) else report.get("repo_url"),
                "scores": report.get("scores", {}),
                "total_score": report.get("final_scores", {}).get("total_score") if isinstance(report.get("final_scores"), dict) else report.get("total_score"),
                "commit_count": report.get("commit_count", 0),
                "file_count": report.get("file_count", 0),
                "lines_of_code": report.get("lines_of_code", 0),
                "languages": report.get("languages", {}),
                "tech_stack": report.get("stack", []),
                "top_contributors": sorted(
                    [
                        {"name": author, "commits": stats if isinstance(stats, int) else stats.get("commits", 0)}
                        for author, stats in (report.get("team", {}) if isinstance(report.get("team", {}), dict) else {}).items()
                    ],
                    key=lambda x: x["commits"],
                    reverse=True
                )[:3],
                "positive_feedback": report.get("positive_feedback"),
                "constructive_feedback": report.get("constructive_feedback"),
                "overall_recommendation": report.get("overall_recommendation"),
                "verdict": report.get("verdict"),
                "verdict_reasoning": report.get("verdict_reasoning"),
            }
            for index, report in enumerate(normalized_reports)
        ]

        return merged_report

    @staticmethod
    def _analyze_single_repository(
        team_id: UUID,
        job_id: UUID,
        repo_url: str,
        team_name: str,
        openai_key: str,
        project_statement: str | None,
        repo_index: int,
        repo_total: int,
        manual_archetype: str | None = None,
    ) -> Dict[str, Any]:
        """Run the pipeline for one repository and return the analysis report."""
        tracker = ProgressTracker(job_id)
        output_slug = str(repo_url.rstrip('/').split('/')[-1].replace('.git', '') or team_id)
        output_dir = os.path.join(f"reports/{team_name or str(team_id)}", output_slug)
        os.makedirs(output_dir, exist_ok=True)

        providers = []
        print(f"\n{'='*60}")
        print(f"🚀 Starting Analysis [{repo_index}/{repo_total}]: {repo_url}")
        print(f"{'='*60}\n")

        def progress_callback(stage: str, progress: int):
            tracker.update(f"{stage} [{repo_index}/{repo_total}]", progress)

        final_report = build_pipeline(
            repo_url=repo_url,
            output_dir=output_dir,
            providers=providers,
            openai_key=openai_key,
            progress_callback=progress_callback,
            team_id=team_id,
            project_statement=project_statement,
            manual_archetype=manual_archetype,
        )

        if final_report and "final_report" in final_report:
            report = final_report["final_report"]
        else:
            report = final_report

        gh_token = os.getenv("GH_API_KEY") or os.getenv("GITHUB_TOKEN")
        if gh_token and repo_url:
            try:
                languages = AnalyzerService._fetch_github_languages(repo_url, gh_token)
                if languages:
                    print(f"      📝 Fetched language data: {list(languages.keys())}")
                    if isinstance(final_report, dict) and "final_report" in final_report:
                        final_report["final_report"]["languages"] = languages
                        report = final_report["final_report"]
                    elif isinstance(final_report, dict):
                        final_report["languages"] = languages
                        report = final_report
            except Exception as e:
                print(f"      ⚠️  Failed to fetch languages: {e}")

        if isinstance(report, dict):
            api_call_tracking = report.get("api_call_tracking")
            if not isinstance(api_call_tracking, dict):
                api_call_tracking = {}
            api_call_tracking["openai_models_list_preflight_calls"] = 1
            report["api_call_tracking"] = api_call_tracking

        return report

    
    @staticmethod
    def analyze_repository(team_id: UUID, job_id: UUID, repo_url: str, team_name: str = None) -> Dict[str, Any]:
        """
        Run full analysis pipeline on a repository
        
        Args:
            team_id: UUID of the team (parameter renamed from project_id for clarity)
            job_id: UUID of the analysis job
            repo_url: GitHub repository URL
            team_name: Optional team name
            
        Returns:
            Analysis report dictionary
        """
        tracker = ProgressTracker(job_id)
        
        try:
            # Update team status
            TeamCRUD.update_team_status(team_id, "analyzing")
            tracker.update("starting")
            
            # Prepare output directory
            output_dir = f"reports/{team_name or str(team_id)}"
            os.makedirs(output_dir, exist_ok=True)
            
            # Get API keys from environment
            openai_key = os.getenv("OPENAI_API_KEY")
            
            # Validate OpenAI API key before starting analysis
            if not openai_key:
                raise ValueError("OPENAI_API_KEY is not configured. Cannot run analysis.")
            
            if not openai_key.startswith("sk-"):
                raise ValueError(
                    f"OPENAI_API_KEY appears invalid (starts with '{openai_key[:5]}...'). "
                    f"Valid keys start with 'sk-'. Check your .env file."
                )
            
            # Pre-flight check: verify the key works before spending time on analysis
            try:
                from openai import OpenAI
                test_client = OpenAI(api_key=openai_key)
                test_client.models.list()  # Lightweight API call to verify key
                print(f"      ✅ OpenAI API key validated")
            except Exception as e:
                raise RuntimeError(
                    f"OpenAI API key validation failed: {e}. "
                    f"Fix your OPENAI_API_KEY before running analysis."
                ) from e

            # LLM providers for forensics (currently disabled by default)
            providers = []  # Can be populated from config if needed

            # Fetch project_statement from team metadata for project-aware evaluation
            project_statement = None
            manual_archetype = None
            try:
                from src.api.backend.database import get_supabase_admin_client
                supabase = get_supabase_admin_client()
                team_result = supabase.table("teams").select("repo_url, metadata").eq("id", str(team_id)).execute()
                if team_result.data:
                    metadata = team_result.data[0].get("metadata") or {}
                    project_statement = AnalyzerService._extract_project_statement(metadata)
                    if isinstance(metadata, dict):
                        manual_archetype = metadata.get("project_profile", {}).get("manual_archetype")
                    if project_statement:
                        print(f"      📋 Project context: {project_statement[:80]}{'...' if len(project_statement) > 80 else ''}")
                    else:
                        print("      ⚠️  Project context missing in metadata; evaluator will infer from repository signals.")
            except Exception as e:
                print(f"      ⚠️  Failed to fetch project_statement: {e}")

            repo_urls = AnalyzerService._get_team_repo_urls(team_id, repo_url)
            if not repo_urls:
                raise ValueError("Team has no repository URL")

            reports = []
            for index, current_repo_url in enumerate(repo_urls, start=1):
                # Augment the prompt context for multi-repo projects
                context_statement = project_statement or ""
                if len(repo_urls) > 1:
                    multi_repo_context = (
                        f"\n\nCRITICAL MULTI-REPO CONTEXT: This codebase is one part of a {len(repo_urls)}-repository system "
                        f"({index}/{len(repo_urls)}). Do NOT penalize this repository for \"missing\" components "
                        f"(like missing frontend, missing backend, or missing db integrations) if it is clearly a specialized part "
                        f"of a larger distributed product. Evaluate it strictly on its own merits."
                    )
                    context_statement = f"{context_statement}{multi_repo_context}".strip()
                
                report = AnalyzerService._analyze_single_repository(
                    team_id=team_id,
                    job_id=job_id,
                    repo_url=current_repo_url,
                    team_name=team_name or str(team_id),
                    openai_key=openai_key,
                    project_statement=context_statement or None,
                    repo_index=index,
                    repo_total=len(repo_urls),
                    manual_archetype=manual_archetype,
                )
                reports.append(report)

            report = AnalyzerService._merge_repository_reports(reports, repo_urls)

            # Save merged results to database
            tracker.update("aggregation", 95)
            success = DataMapper.save_analysis_results(team_id, report)
            
            if not success:
                raise Exception("Failed to save analysis results to database")
            
            # Mark job as completed
            tracker.complete()
            
            print(f"\n{'='*60}")
            print(f"✅ Analysis Complete!")
            print(f"{'='*60}\n")
            
            return report
            
        except Exception as e:
            # Mark job as failed
            error_msg = str(e)
            print(f"\n{'='*60}")
            print(f"❌ Analysis Failed: {error_msg}")
            print(f"{'='*60}\n")
            
            tracker.fail(error_msg)
            TeamCRUD.update_team_status(team_id, "failed")
            
            raise
        
        finally:
            pass
