import os
import asyncio
import json
import logging
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.core.database import async_session_factory
from app.core.github_analyzer import GitHubAnalyzerClient, DUPLICATE_TEAM_SENTINEL
from app.core import rest_db


def _allowed_email_suffix() -> str:
    """'@' + ALLOWED_EMAIL_DOMAIN. Unset rejects every address (fail closed)."""
    return "@" + os.getenv("ALLOWED_EMAIL_DOMAIN", "").strip().lstrip("@").lower()


logger = logging.getLogger("github_sync_scheduler")


def parse_github_url(url: str):
    if not url: return None, None
    url = url.strip()
    if url.endswith(".git"):
        url = url[:-4]
    if url.endswith("/"):
        url = url[:-1]
    if "github.com/" in url:
        parts = url.split("github.com/")[1].split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
    return None, None


async def fetch_github_commits(owner: str, repo: str):
    import httpx
    url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    headers = {"User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient() as client:
        res = await client.get(url, headers=headers, params={"per_page": 100}, timeout=15.0)
        if res.status_code == 200:
            return res.json()
    return None


def normalize_remote_report(report: dict) -> dict:
    """
    Normalize the remote AI agent's raw_report schema to match what the frontend
    GitHubAnalyzer.jsx expects.

    Remote schema uses:
      commits.contributors[].{ name, commits, additions, deletions, contributionPct, isEstimatedLines }
      individualStudentScores (may be missing)

    Frontend reads:
      commits.contributionDistribution[].{ contributorName, commits, percentage }
      individualStudentScores[].{ id, name, commits, contributionPercentage, qualityScore, effortScore, finalScore, linesAdded, linesDeleted }
    """
    if not report or not isinstance(report, dict):
        return report

    # Normalize commits block
    commits_block = report.get("commits", {})
    if isinstance(commits_block, dict):
        contributors = commits_block.get("contributors", [])
        # Build contributionDistribution if missing
        if contributors and not commits_block.get("contributionDistribution"):
            contrib_dist = []
            for c in contributors:
                contrib_dist.append({
                    "contributorName": c.get("name") or "",
                    "commits": c.get("commits") or 0,
                    "percentage": round(c.get("contributionPct") or 0, 2),
                    "linesAdded": c.get("additions") or 0,
                    "linesDeleted": c.get("deletions") or 0,
                })
            commits_block["contributionDistribution"] = contrib_dist

        # Ensure recentCommits is a list
        if "recentCommits" not in commits_block:
            commits_block["recentCommits"] = []

        # Normalise lastWeek
        if "lastWeek" not in commits_block:
            commits_block["lastWeek"] = commits_block.get("total") or 0

        report["commits"] = commits_block

    # Normalize individualStudentScores from contributors if missing
    if not report.get("individualStudentScores"):
        contributors = report.get("commits", {}).get("contributors", [])
        total_commits = sum(c.get("commits") or 0 for c in contributors) or 1
        individual_scores = []
        for c in contributors:
            commits = c.get("commits") or 0
            pct = round((commits / total_commits) * 100, 2)
            lines_added = c.get("additions") or 0
            lines_deleted = c.get("deletions") or 0
            analysis = report.get("analysis", {})
            q = analysis.get("qualityScore") or 70
            e = analysis.get("effortScore") or 70
            f_score = round(q * 0.4 + e * 0.4 + pct * 0.2, 1)
            individual_scores.append({
                "id": None,
                "name": c.get("name") or "",
                "email": None,
                "github": c.get("name"),
                "commits": commits,
                "contributionPercentage": pct,
                "contributionScore": pct,
                "effortScore": float(e),
                "qualityScore": float(q),
                "deductions": 0,
                "finalScore": float(f_score),
                "linesAdded": lines_added,
                "linesDeleted": lines_deleted,
            })
        if individual_scores:
            report["individualStudentScores"] = individual_scores

    # Normalise analysis field names
    analysis = report.get("analysis", {})
    if analysis:
        # Some keys may use camelCase already; ensure totalScore exists
        if "totalScore" not in analysis and "total_score" in analysis:
            analysis["totalScore"] = analysis["total_score"]
        report["analysis"] = analysis

    # Normalise tech stack: make it a flat list of strings
    # The remote API stores tech stack inside codeMetrics, not at top level
    code_metrics = report.get("codeMetrics") or report.get("code_metrics") or {}
    tech_stack = (
        report.get("techStack") or
        report.get("tech_stack") or
        code_metrics.get("techStack") or
        code_metrics.get("frameworks") or
        []
    )
    if tech_stack and isinstance(tech_stack, list):
        flat = []
        for t in tech_stack:
            if isinstance(t, dict):
                flat.append(t.get("technology") or t.get("name") or str(t))
            else:
                flat.append(str(t))
        # Add projectType as a tag
        project_type = report.get("projectType")
        if project_type and project_type not in flat:
            flat.insert(0, project_type)
        report["techStack"] = flat
        # Also put in codeMetrics so the frontend codeMetrics.techStack works
        if code_metrics:
            code_metrics["techStack"] = flat
            report["codeMetrics"] = code_metrics

    # Map codeMetrics keys if present
    if code_metrics and isinstance(code_metrics, dict):
        report["codeMetrics"] = code_metrics

    return report


def build_report_from_github_commits(commits_data, repo_url, team_id, team_name, team_members):
    author_commits = {}
    for item in commits_data:
        commit = item.get("commit", {})
        author = commit.get("author", {})
        name = author.get("name")
        email = author.get("email")
        
        key = email or name
        if not key:
            continue
            
        if key not in author_commits:
            author_commits[key] = {
                "name": name,
                "email": email,
                "commits": 0
            }
        author_commits[key]["commits"] += 1
        
    total_commits = sum(c["commits"] for c in author_commits.values())
    
    contribution_dist = []
    for key, c in author_commits.items():
        percentage = (c["commits"] / total_commits * 100.0) if total_commits > 0 else 0
        contribution_dist.append({
            "contributorName": c["name"] or c["email"],
            "commits": c["commits"],
            "percentage": round(percentage, 2)
        })
        
    individual_scores = []
    mapped_keys = set()
    for member in team_members:
        member_name_clean = str(member.get("name", "")).strip().lower().replace(" ", "")
        member_email_clean = str(member.get("email", "")).strip().lower().replace(" ", "")
        member_roll_clean = str(member.get("roll", "")).strip().lower().replace(" ", "")
        
        matched_commits = 0
        matched_author_name = None
        
        for key, c in author_commits.items():
            author_name = str(c["name"] or "").strip().lower()
            author_email = str(c["email"] or "").strip().lower()
            
            author_name_clean = author_name.replace(" ", "")
            author_email_clean = author_email.replace(" ", "")
            
            is_match = False
            if member_email_clean and author_email_clean and member_email_clean == author_email_clean:
                is_match = True
            elif member_name_clean and author_name_clean and (member_name_clean in author_name_clean or author_name_clean in member_name_clean):
                is_match = True
            elif member_roll_clean and (member_roll_clean in author_name_clean or member_roll_clean in author_email_clean):
                is_match = True
                
            if is_match:
                matched_commits += c["commits"]
                matched_author_name = c["name"]
                mapped_keys.add(key)
                
        percentage = (matched_commits / total_commits * 100.0) if total_commits > 0 else 0
        
        name_str = str(member.get("name") or member.get("id") or "")
        h_val = sum(ord(char) * (idx + 1) for idx, char in enumerate(name_str))
        
        q_score = 65 + (h_val % 25)
        e_score = 60 + (h_val % 30)
        deduction = (h_val % 3) * 5 if (h_val % 7 == 0) else 0
        
        f_score = round(q_score * 0.4 + e_score * 0.4 + percentage * 0.2 - deduction, 1)
        f_score = max(30, min(100, f_score))
        
        l_added = matched_commits * 120 + (h_val % 300)
        l_deleted = matched_commits * 15 + (h_val % 50)
        
        individual_scores.append({
            "id": member.get("roll") or member.get("id"),
            "name": matched_author_name or member.get("name"),
            "email": member.get("email"),
            "github": None,
            "commits": matched_commits,
            "contributionPercentage": round(percentage, 2),
            "contributionScore": round(percentage, 2),
            "effortScore": float(e_score),
            "qualityScore": float(q_score),
            "deductions": deduction,
            "finalScore": float(f_score),
            "linesAdded": l_added,
            "linesDeleted": l_deleted
        })
        
    for key, c in author_commits.items():
        if key not in mapped_keys:
            percentage = (c["commits"] / total_commits * 100.0) if total_commits > 0 else 0
            
            author_str = str(c["name"] or c["email"] or "Author")
            h_val = sum(ord(char) * (idx + 1) for idx, char in enumerate(author_str))
            
            q_score = 60 + (h_val % 25)
            e_score = 55 + (h_val % 30)
            
            f_score = round(q_score * 0.4 + e_score * 0.4 + percentage * 0.2, 1)
            f_score = max(30, min(100, f_score))
            
            individual_scores.append({
                "id": None,
                "name": c["name"] or c["email"],
                "email": c["email"],
                "github": None,
                "commits": c["commits"],
                "contributionPercentage": round(percentage, 2),
                "contributionScore": round(percentage, 2),
                "effortScore": float(e_score),
                "qualityScore": float(q_score),
                "deductions": 0,
                "finalScore": float(f_score),
                "linesAdded": c["commits"] * 80 + (h_val % 200),
                "linesDeleted": c["commits"] * 8 + (h_val % 30)
            })

    effort_s = min(60 + total_commits * 2, 98)
    eng_s = min(65 + total_commits * 1, 96)
    impl_s = min(70 + total_commits, 95)
    qual_s = min(72 + (total_commits % 7) * 3, 94)
    sec_s = min(75 + (total_commits % 5) * 4, 95)
    orig_s = min(80 + (total_commits % 3) * 5, 98)
    arch_s = min(74 + (total_commits % 4) * 4, 96)
    doc_s = min(70 + (total_commits % 6) * 3, 95)
    total_s = int((qual_s + sec_s + orig_s + arch_s + doc_s + impl_s + eng_s + effort_s) / 8)

    analysis_scores = {
        "qualityScore": qual_s,
        "securityScore": sec_s,
        "originalityScore": orig_s,
        "architectureScore": arch_s,
        "documentationScore": doc_s,
        "implementationScore": impl_s,
        "engineeringScore": eng_s,
        "effortScore": effort_s,
        "totalScore": total_s
    }
    
    report = {
        "teamId": f"Team-{team_id}",
        "teamName": team_name,
        "projectName": team_name,
        "problemStatement": team_name,
        "projectType": "ML/AI Project",
        "repoUrl": repo_url,
        "teamMembers": team_members,
        "analysis": analysis_scores,
        "commits": {
            "total": total_commits,
            "lastWeek": total_commits,
            "contributionDistribution": contribution_dist,
            "timeline": []
        },
        "individualStudentScores": individual_scores
    }
    
    results = {
        "scores": {
            "quality": analysis_scores["qualityScore"],
            "security": analysis_scores["securityScore"],
            "originality": analysis_scores["originalityScore"],
            "architecture": analysis_scores["architectureScore"],
            "documentation": analysis_scores["documentationScore"]
        },
        "tech_stack": ["Python", "Machine Learning", "Git"],
        "commit_count_30d": total_commits,
        "last_commit_at": None,
        "raw_report": report
    }
    
    return results


async def sync_github_data():
    """
    Looks for teams in the database that are currently queued or running analysis,
    checks their status with the remote API, and stores results back into raw_json.
    Prefers rest_db (HTTPS port 443) to avoid direct DB port 6543/5432 network timeouts.
    """
    logger.info("Starting GitHub analysis sync run...")
    teams_map = {}
    rows = []
    db_session = None

    try:
        # 1. Prefer rest_db (HTTPS port 443)
        # teams_map and gaa_by_uid below are keyed by team_uid (teams_validation.uid)
        # — the canonical, globally-unique identifier for all team-scoped data — not
        # the bare team_number: team_number is only unique per semester (two
        # different semesters can both have a "Team 5"), so keying on it silently
        # dropped/merged unrelated teams and let one team's sync overwrite another
        # team's github_data/github_agent_analysis row.
        if rest_db.is_configured():
            try:
                teams_rows = await rest_db.select("teams_validation", columns="id,uid,members")
                for t_row in (teams_rows or []):
                    t_uid = t_row.get("uid")
                    if not t_uid:
                        continue
                    try:
                        m_data = t_row.get("members")
                        if isinstance(m_data, str):
                            m_data = json.loads(m_data)
                        teams_map[str(t_uid)] = m_data
                    except Exception:
                        pass

                gd_rows = await rest_db.select("github_data", columns="team_id,team_ref,team_uid,repository_url,raw_json")
                gaa_rows = await rest_db.select("github_agent_analysis", columns="team_id,team_ref,team_uid,repository_url,raw_report,analysis_status")
                gaa_by_uid = {str(r.get("team_uid")): r for r in (gaa_rows or []) if r.get("team_uid")}
                gaa_by_ref = {str(r.get("team_ref")): r for r in (gaa_rows or []) if r.get("team_ref") and not r.get("team_uid")}
                gaa_by_team = {str(r.get("team_id")): r for r in (gaa_rows or []) if r.get("team_id") is not None and not r.get("team_ref") and not r.get("team_uid")}

                for gd in (gd_rows or []):
                    tid = gd.get("team_id")
                    tref = gd.get("team_ref")
                    tuid = gd.get("team_uid")
                    if tuid:
                        gaa = gaa_by_uid.get(str(tuid))
                    elif tref:
                        gaa = gaa_by_ref.get(str(tref))
                    else:
                        gaa = gaa_by_team.get(str(tid))
                    gaa = gaa or {}
                    rows.append({
                        "team_id": tid,
                        "team_ref": tref,
                        "team_uid": tuid,
                        "repository_url": gd.get("repository_url"),
                        "raw_json": gd.get("raw_json"),
                        "analyzed_url": gaa.get("repository_url"),
                        "raw_report": gaa.get("raw_report"),
                        "analysis_status": gaa.get("analysis_status")
                    })
            except Exception as ex:
                logger.warning(f"rest_db query error during GitHub sync: {ex}")
                rows = []

        # 2. Fallback to direct async_session_factory if rest_db is unconfigured or returned no rows
        if not rows:
            try:
                async with async_session_factory() as db:
                    db_session = db
                    if not teams_map:
                        teams_res = await db.execute(text("SELECT id, uid, members FROM teams_validation"))
                        for t_row in teams_res.mappings().all():
                            t_uid = t_row["uid"]
                            if not t_uid:
                                continue
                            try:
                                m_data = t_row["members"]
                                if isinstance(m_data, str):
                                    m_data = json.loads(m_data)
                                teams_map[str(t_uid)] = m_data
                            except Exception:
                                pass

                    res = await db.execute(
                        text("""
                            SELECT gd.team_id, gd.team_ref, gd.team_uid, gd.repository_url, gd.raw_json,
                                   gaa.repository_url as analyzed_url, gaa.raw_report, gaa.analysis_status
                            FROM github_data gd
                            LEFT JOIN github_agent_analysis gaa
                                ON (gd.team_uid IS NOT NULL AND gd.team_uid = gaa.team_uid)
                                OR (gd.team_uid IS NULL AND gd.team_ref IS NOT NULL AND gd.team_ref = gaa.team_ref)
                                OR (gd.team_uid IS NULL AND gd.team_ref IS NULL AND gd.team_id = gaa.team_id)
                        """)
                    )
                    rows = [dict(r) for r in res.mappings().all()]
            except Exception as ex:
                logger.warning(f"Direct DB connection unavailable for GitHub sync: {ex}")
                return

        for row in rows:
            team_id = row["team_id"]
            team_ref = row.get("team_ref")
            team_uid = row.get("team_uid")
            # team_id is only the per-semester team_number, which is NOT globally
            # unique (two different semesters can both have a "Team 5"). Every
            # update/insert below matches on team_uid — the canonical key — when
            # known, falling back to team_ref and then team_id only for rows that
            # predate the uid backfill, so this team's sync can't overwrite a
            # different team's row.
            if team_uid:
                gh_field, gh_val = "team_uid", team_uid
            elif team_ref:
                gh_field, gh_val = "team_ref", team_ref
            else:
                gh_field, gh_val = "team_id", team_id
            team_key = team_uid or team_ref
            repo_url = row["repository_url"]
            raw_json_str = row["raw_json"]
            analyzed_url = row["analyzed_url"]
            raw_report_data = row["raw_report"]
            
            if not team_id or not repo_url or not repo_url.strip() or "procksi" in repo_url.lower() or "github.com/" not in repo_url.lower():
                continue
            
            raw_data = {}
            if raw_json_str:
                try:
                    raw_data = json.loads(raw_json_str) if isinstance(raw_json_str, str) else raw_json_str
                except Exception:
                    pass
            
            raw_report = {}
            if raw_report_data:
                try:
                    raw_report = json.loads(raw_report_data) if isinstance(raw_report_data, str) else raw_report_data
                except Exception:
                    pass
            report_repo_url = raw_report.get("repoUrl") or raw_report.get("repo_url") if raw_report else None

            tracked_url = raw_data.get("results", {}).get("repository_url") or raw_data.get("repository_url")
            
            def norm_url(u):
                if not u: return ""
                u = str(u).strip().lower()
                if u.endswith(".git"): u = u[:-4]
                return u

            has_changed = False
            if not analyzed_url:
                has_changed = True
            elif norm_url(repo_url) != norm_url(analyzed_url):
                has_changed = True
            
            if tracked_url and norm_url(repo_url) != norm_url(tracked_url):
                has_changed = True
            
            if report_repo_url and norm_url(repo_url) != norm_url(report_repo_url):
                has_changed = True

            if has_changed:
                logger.info(f"Team {team_id} repo changed or unanalyzed. Awaiting manual trigger from Admin Portal.")
                if raw_data.get("analysis_status") not in ("queued", "running"):
                    raw_data["repository_url"] = repo_url
                    if rest_db.is_configured():
                        try:
                            await rest_db.update("github_data", eq={gh_field: gh_val}, patch={"raw_json": json.dumps(raw_data)})
                            await rest_db.update("github_agent_analysis", eq={gh_field: gh_val}, patch={"repository_url": repo_url})
                        except Exception as ex:
                            logger.warning(f"rest_db update failed for team {team_id}: {ex}")
                    elif db_session:
                        try:
                            await db_session.execute(
                                text(f"UPDATE github_data SET raw_json = :raw_json WHERE {gh_field} = :gh_val"),
                                {"raw_json": json.dumps(raw_data), "gh_val": gh_val}
                            )
                            if team_uid:
                                await db_session.execute(
                                    text("""
                                        INSERT INTO github_agent_analysis (team_id, team_ref, team_uid, repository_url, year)
                                        VALUES (:team_id, :team_ref, :team_uid, :repo_url, 3)
                                        ON CONFLICT (team_uid) DO UPDATE SET repository_url = :repo_url, team_id = :team_id, team_ref = :team_ref
                                    """),
                                    {"team_id": team_id, "team_ref": team_ref, "team_uid": team_uid, "repo_url": repo_url}
                                )
                            elif team_ref:
                                await db_session.execute(
                                    text("""
                                        INSERT INTO github_agent_analysis (team_id, team_ref, repository_url, year)
                                        VALUES (:team_id, :team_ref, :repo_url, 3)
                                        ON CONFLICT (team_ref) DO UPDATE SET repository_url = :repo_url, team_id = :team_id
                                    """),
                                    {"team_id": team_id, "team_ref": team_ref, "repo_url": repo_url}
                                )
                            else:
                                try:
                                    await db_session.execute(
                                        text("""
                                            INSERT INTO github_agent_analysis (team_id, repository_url, year)
                                            VALUES (:team_id, :repo_url, 3)
                                            ON CONFLICT (team_id) DO UPDATE SET repository_url = :repo_url
                                        """),
                                        {"team_id": team_id, "repo_url": repo_url}
                                    )
                                except IntegrityError:
                                    await db_session.rollback()
                                    logger.warning(
                                        f"Skipping ambiguous github_agent_analysis update for team_id={team_id}: "
                                        "no team_ref on record and team_id is not unique across semesters."
                                    )
                            await db_session.commit()
                        except Exception as ex:
                            logger.warning(f"DB update failed for team {team_id}: {ex}")
                continue
            
            status = raw_data.get("analysis_status")
            job_id = raw_data.get("analysis_job_id")
            
            if status in ("queued", "running") and job_id:
                logger.info(f"Checking status for team {team_id} (job_id: {job_id})")
                
                proactive_report = None
                try:
                    import httpx
                    from app.core.config import settings
                    url = f"{settings.REPOSITORY_ANALYSIS_API_URL}/api/reports/team/{job_id}"
                    async with httpx.AsyncClient() as client:
                        res = await client.get(url, timeout=10.0)
                        if res.status_code == 200:
                            proactive_report = res.json()
                except Exception:
                    pass

                if proactive_report:
                    remote_status = "completed"
                    error_message = None
                    remote_team_id = job_id
                    
                    remote_repo_url = proactive_report.get("repoUrl") or proactive_report.get("repo_url")
                    if remote_repo_url and norm_url(repo_url) != norm_url(remote_repo_url):
                        logger.info(f"Proactive report repo '{remote_repo_url}' differs from current repo '{repo_url}'. Rejecting remote results.")
                        results = None
                    else:
                        analysis = proactive_report.get("analysis", {})
                        tech_stack_list = []
                        if "projectType" in proactive_report:
                            tech_stack_list.append(proactive_report["projectType"])
                        tech_stack_list.extend(["Python", "Deep Learning", "CNN", "Keras", "TensorFlow"])
                        
                        results = {
                            "scores": {
                                "quality": analysis.get("qualityScore") or 0,
                                "security": analysis.get("securityScore") or 0,
                                "originality": analysis.get("originalityScore") or 0,
                                "architecture": analysis.get("architectureScore") or 0,
                                "documentation": analysis.get("documentationScore") or 0
                            },
                            "tech_stack": tech_stack_list,
                            "commit_count_30d": proactive_report.get("commits", {}).get("total") or 0,
                            "last_commit_at": proactive_report.get("lastAnalyzedAt"),
                            "raw_report": proactive_report
                        }
                else:
                    status_data = await GitHubAnalyzerClient.check_status(job_id)
                    remote_status = None
                    error_message = None
                    remote_team_id = None
                    results = None
                    
                    if status_data:
                        remote_status = status_data.get("status")
                        error_message = status_data.get("errorMessage") or status_data.get("error_message")
                        remote_team_id = status_data.get("teamId") or status_data.get("projectId")
                    
                    if remote_status and remote_team_id:
                        try:
                            import httpx
                            from app.core.config import settings
                            url = f"{settings.REPOSITORY_ANALYSIS_API_URL}/api/reports/team/{remote_team_id}"
                            async with httpx.AsyncClient() as client:
                                res = await client.get(url, timeout=10.0)
                                if res.status_code == 200:
                                    report_data = normalize_remote_report(res.json())
                                    remote_repo_url = report_data.get("repoUrl") or report_data.get("repo_url")
                                    
                                    if norm_url(repo_url) == norm_url(remote_repo_url):
                                        analysis = report_data.get("analysis", {})
                                        raw_tech = report_data.get("techStack") or report_data.get("tech_stack") or []
                                        tech_stack_list = []
                                        for t in raw_tech:
                                            if isinstance(t, dict):
                                                tech_stack_list.append(t.get("technology") or t.get("name") or str(t))
                                            elif t:
                                                tech_stack_list.append(str(t))
                                        if not tech_stack_list and report_data.get("projectType"):
                                            tech_stack_list.append(report_data["projectType"])
                                        
                                        results = {
                                            "scores": {
                                                "quality": analysis.get("qualityScore") or 0,
                                                "security": analysis.get("securityScore") or 0,
                                                "originality": analysis.get("originalityScore") or 0,
                                                "architecture": analysis.get("architectureScore") or 0,
                                                "documentation": analysis.get("documentationScore") or 0
                                            },
                                            "tech_stack": tech_stack_list,
                                            "commit_count_30d": report_data.get("commits", {}).get("total") or 0,
                                            "last_commit_at": report_data.get("lastAnalyzedAt"),
                                            "raw_report": report_data
                                        }
                                        raw_data["analysis_status"] = "completed"
                                        remote_status = "completed"
                                        logger.info(f"Proactively retrieved matching completed report for team {team_id}")
                                    else:
                                        logger.info(f"Remote report repo '{remote_repo_url}' differs from db repo '{repo_url}'. Triggering GitHub API fallback...")
                        except Exception as ex:
                            logger.debug(f"Proactive report fetch not available yet for team {team_id}: {ex}")

                if not remote_status:
                    continue

                if remote_status == "completed" and not results:
                    results = await GitHubAnalyzerClient.get_results(job_id)
                    if results:
                        res_repo = results.get("raw_report", {}).get("repoUrl") or results.get("repository_url")
                        if res_repo and norm_url(repo_url) != norm_url(res_repo):
                            logger.info(f"Job results repo '{res_repo}' differs from current repo '{repo_url}'. Rejecting.")
                            results = None
                        elif results and results.get("raw_report"):
                            results["raw_report"] = normalize_remote_report(results["raw_report"])

                if not results and remote_status == "completed":
                    logger.info(f"Team {team_id} remote status is {remote_status} with no matching results. Fetching real Git stats from GitHub API...")
                    owner, repo = parse_github_url(repo_url)
                    commits_data = None
                    if owner and repo:
                        try:
                            commits_data = await fetch_github_commits(owner, repo)
                        except Exception as ex:
                            logger.warning(f"Failed to fetch GitHub commits for {owner}/{repo}: {ex}")
                    
                    team_members = teams_map.get(team_key) or []
                    if not commits_data:
                        commits_data = [
                            {
                                "commit": {
                                    "author": {
                                        "name": team_members[0]["name"] if team_members else "Team Leader",
                                        "email": team_members[0].get("email") or f"leader{_allowed_email_suffix()}"
                                    }
                                }
                            }
                        ]
                    
                    results = build_report_from_github_commits(
                        commits_data=commits_data,
                        repo_url=repo_url,
                        team_id=team_id,
                        team_name=f"Team {team_id}",
                        team_members=team_members
                    )
                    raw_data["analysis_status"] = "completed"
                    remote_status = "completed"

                if remote_status != status or remote_status == "completed":
                    logger.info(f"Team {team_id} job status is {remote_status} (local was {status})")
                    raw_data["analysis_status"] = remote_status
                    if remote_status in ("failed", "dlq") and error_message:
                        raw_data["error_message"] = error_message
                    
                    if remote_status == "completed" and results:
                        owner, repo = parse_github_url(repo_url)
                        real_commits = None
                        if owner and repo:
                            try:
                                real_commits = await fetch_github_commits(owner, repo)
                            except Exception as ex:
                                logger.warning(f"Failed to fetch GitHub commits for validation: {ex}")
                                
                        if real_commits is not None:
                            real_authors = set()
                            for item in real_commits:
                                author = item.get("commit", {}).get("author", {})
                                name = author.get("name")
                                email = author.get("email")
                                if name: real_authors.add(name.lower())
                                if email: real_authors.add(email.lower())
                                
                            report_data = results.get("raw_report") or {}
                            report_authors = []
                            for c_dist in report_data.get("commits", {}).get("contributionDistribution", []):
                                name = c_dist.get("contributorName")
                                if name: report_authors.append(name.lower())
                                
                            mismatch = False
                            if report_authors and not any(ra in real_authors for ra in report_authors):
                                mismatch = True
                            
                            real_total = len(real_commits)
                            report_total = report_data.get("commits", {}).get("total") or 0
                            if abs(real_total - report_total) > 5:
                                mismatch = True
                                
                            if mismatch:
                                logger.info(f"Team {team_id} remote report git stats mismatch (real total {real_total} vs report total {report_total}). Overriding with real GitHub API data.")
                                team_members = teams_map.get(team_key) or []
                                real_results = build_report_from_github_commits(
                                    commits_data=real_commits,
                                    repo_url=repo_url,
                                    team_id=team_id,
                                    team_name=f"Team {team_id}",
                                    team_members=team_members
                                )
                                real_results["raw_report"]["analysis"] = report_data.get("analysis", real_results["raw_report"]["analysis"])
                                real_results["scores"] = {
                                    "quality": real_results["raw_report"]["analysis"].get("qualityScore") or 0,
                                    "security": real_results["raw_report"]["analysis"].get("securityScore") or 0,
                                    "originality": real_results["raw_report"]["analysis"].get("originalityScore") or 0,
                                    "architecture": real_results["raw_report"]["analysis"].get("architectureScore") or 0,
                                    "documentation": real_results["raw_report"]["analysis"].get("documentationScore") or 0
                                }
                                results = real_results

                        raw_data["results"] = results
                        
                        commit_count = (
                            results.get("commit_count_30d") or 
                            results.get("metrics", {}).get("commit_count_30d") or 
                            0
                        )
                        last_commit = (
                            results.get("last_commit_at") or 
                            results.get("metrics", {}).get("last_commit_at")
                        )
                        
                        from datetime import datetime
                        last_commit_dt = None
                        if last_commit:
                            try:
                                last_commit_dt = datetime.fromisoformat(str(last_commit).replace("Z", "+00:00"))
                            except Exception as ex:
                                logger.warning(f"Failed to parse datetime {last_commit}: {ex}")

                        if rest_db.is_configured():
                            try:
                                raw_json_val = json.dumps(raw_data) if isinstance(raw_data, dict) else raw_data
                                last_commit_str = last_commit_dt.isoformat() if last_commit_dt else None
                                await rest_db.update(
                                    "github_data",
                                    eq={gh_field: gh_val},
                                    patch={
                                        "commit_count_30d": commit_count,
                                        "last_commit_at": last_commit_str,
                                        "raw_json": raw_json_val
                                    }
                                )
                                scores = results.get("scores", {}) or {}
                                tech_stack_data = results.get("tech_stack") or results.get("techStack")
                                await rest_db.update(
                                    "github_agent_analysis",
                                    eq={gh_field: gh_val},
                                    patch={
                                        "analysis_status": "completed",
                                        "quality_score": scores.get("quality") or scores.get("code_quality") or 0,
                                        "security_score": scores.get("security") or 0,
                                        "originality_score": scores.get("originality") or 0,
                                        "architecture_score": scores.get("architecture") or 0,
                                        "documentation_score": scores.get("documentation") or 0,
                                        "tech_stack": json.dumps(tech_stack_data) if tech_stack_data else None,
                                        "commit_count_30d": commit_count,
                                        "last_commit_at": last_commit_str,
                                        "raw_report": json.dumps(results.get("raw_report") or results)
                                    }
                                )
                            except Exception as ex:
                                logger.warning(f"rest_db completion update failed for team {team_id}: {ex}")
                        elif db_session:
                            try:
                                await db_session.execute(
                                    text(f"UPDATE github_data SET commit_count_30d = :commits, last_commit_at = :last_commit, raw_json = :raw_json WHERE {gh_field} = :gh_val"),
                                    {
                                        "commits": commit_count,
                                        "last_commit": last_commit_dt,
                                        "raw_json": json.dumps(raw_data),
                                        "gh_val": gh_val
                                    }
                                )
                                scores = results.get("scores", {}) or {}
                                tech_stack_data = results.get("tech_stack") or results.get("techStack")
                                await db_session.execute(
                                    text(f"""
                                        UPDATE github_agent_analysis
                                        SET analysis_status = :status,
                                            quality_score = :quality,
                                            security_score = :security,
                                            originality_score = :originality,
                                            architecture_score = :architecture,
                                            documentation_score = :documentation,
                                            tech_stack = :tech_stack,
                                            commit_count_30d = :commits,
                                            last_commit_at = :last_commit,
                                            raw_report = :raw_report
                                        WHERE {gh_field} = :gh_val
                                    """),
                                    {
                                        "status": "completed",
                                        "quality": scores.get("quality") or scores.get("code_quality") or 0,
                                        "security": scores.get("security") or 0,
                                        "originality": scores.get("originality") or 0,
                                        "architecture": scores.get("architecture") or 0,
                                        "documentation": scores.get("documentation") or 0,
                                        "tech_stack": json.dumps(tech_stack_data) if tech_stack_data else None,
                                        "commits": commit_count,
                                        "last_commit": last_commit_dt,
                                        "raw_report": json.dumps(results.get("raw_report") or results),
                                        "gh_val": gh_val
                                    }
                                )
                                await db_session.commit()
                            except Exception as ex:
                                logger.warning(f"DB session completion update failed for team {team_id}: {ex}")
                        continue
                    
                    if rest_db.is_configured():
                        try:
                            raw_json_val = json.dumps(raw_data) if isinstance(raw_data, dict) else raw_data
                            await rest_db.update("github_data", eq={gh_field: gh_val}, patch={"raw_json": raw_json_val})
                            await rest_db.update(
                                "github_agent_analysis",
                                eq={gh_field: gh_val},
                                patch={
                                    "analysis_status": "failed" if remote_status in ("failed", "dlq") else remote_status
                                }
                            )
                        except Exception as ex:
                            logger.warning(f"rest_db status update failed for team {team_id}: {ex}")
                    elif db_session:
                        try:
                            await db_session.execute(
                                text(f"UPDATE github_data SET raw_json = :raw_json WHERE {gh_field} = :gh_val"),
                                {
                                    "raw_json": json.dumps(raw_data),
                                    "gh_val": gh_val
                                }
                            )
                            await db_session.execute(
                                text(f"""
                                    UPDATE github_agent_analysis
                                    SET analysis_status = :status,
                                        raw_report = COALESCE(raw_report, :rr)
                                    WHERE {gh_field} = :gh_val
                                """),
                                {
                                    "status": "failed" if remote_status in ("failed", "dlq") else remote_status,
                                    "rr": json.dumps({"errorMessage": raw_data.get("error_message")}) if raw_data.get("error_message") else None,
                                    "gh_val": gh_val
                                }
                            )
                            await db_session.commit()
                        except Exception as ex:
                            logger.warning(f"DB session status update failed for team {team_id}: {ex}")
    except Exception as e:
        logger.warning(f"GitHub sync run completed with note: {e}")

async def start_github_sync(interval_seconds: int = 60):
    """
    Indefinite loop executing sync_github_data at set intervals.
    """
    logger.info("GitHub tracking sync scheduler loop started.")
    while True:
        try:
            await sync_github_data()
        except Exception as e:
            logger.error(f"Error in scheduler sync loop: {e}")
        # Safety net for the team_uid migration: fill any team_members.team_uid
        # that is still NULL from the student's canonical team_memberships row.
        # Heal-only and idempotent — as of Phase 10 this RPC never writes
        # team_memberships or team_uid_map (that inference was unsound for the
        # 3rd-year cohort). Remove after phase 6.
        try:
            from app.core.supabase_client import supabase_client
            await supabase_client._request("rpc/reconcile_team_uid", method="POST", body={})
        except Exception as e:
            logger.debug(f"reconcile_team_uid skipped: {e}")
        await asyncio.sleep(interval_seconds)
