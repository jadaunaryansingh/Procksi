import argparse
import os
import sys
import csv
import json
import time
from datetime import datetime
from dotenv import load_dotenv

# --- Load Environment Variables ---
load_dotenv()

# --- CONFIGURATION ---
# Default input file - can be overridden via CLI argument or environment variable
INPUT_FILE = os.environ.get("DEFAULT_INPUT_FILE", None) 

# --- Import Core Utils ---
from src.orchestrator.langgraph_adapter import SimpleLangGraph
from src.utils.git_utils import clone_repo, cleanup_repo, list_files
from src.utils.file_utils import read_file, generate_tree_structure

# --- Import Detectors ---
from src.detectors.commit_forensics import analyze_commits
from src.detectors.llm_detector import llm_origin_ensemble
from src.detectors.quality_metrics import analyze_quality
from src.detectors.alg_detector import algorithmic_similarity 
from src.detectors.security_scan import scan_for_secrets
from src.detectors.stack_detector import detect_tech_stack
from src.detectors.product_evaluator import evaluate_product_logic
from src.detectors.maturity_scanner import scan_project_maturity
from src.detectors.structure_analyzer import analyze_structure
from src.detectors.test_coverage_analyzer import analyze_test_coverage
from src.detectors.deployment_verifier import verify_deployment
from src.detectors.documentation_analyzer import analyze_documentation_completeness
from src.detectors.contributor_verifier import analyze_contributor_verification
from src.utils.visualizer import generate_dashboard

# ==========================================
# 1. Pipeline Nodes
# ==========================================

def node_clone_repo(ctx):
    url = ctx.get("repo_url")
    progress_callback = ctx.get("progress_callback")
    
    if progress_callback:
        progress_callback("cloning", 10)
    
    print(f"\n[1/10] 📥 Cloning repository...")
    try:
        repo_path = clone_repo(url, depth=None)
        return {"repo_path": repo_path}
    except Exception as e:
        print(f"      ❌ Clone failed: {e}")
        raise

def node_stack_id(ctx):
    progress_callback = ctx.get("progress_callback")
    
    if progress_callback:
        progress_callback("stack_detection", 20)
    
    print(f"[2/10] 🔎 Identifying Tech Stack...")
    return {"tech_stack": detect_tech_stack(ctx.get("repo_path"))}

def node_structure_analysis(ctx):
    progress_callback = ctx.get("progress_callback")
    
    if progress_callback:
        progress_callback("structure_analysis", 30)
    
    print(f"[3/10] 🏗️  Analyzing Architecture & Organization...")
    return {"structure": analyze_structure(ctx.get("repo_path"))}

def node_maturity_check(ctx):
    progress_callback = ctx.get("progress_callback")
    
    if progress_callback:
        progress_callback("maturity_check", 40)
    
    print(f"[4/10] 🚀 Checking Deployment & Testing Maturity...")
    return {"maturity": scan_project_maturity(ctx.get("repo_path"), repo_url=ctx.get("repo_url"))}

def node_commit_forensics(ctx):
    progress_callback = ctx.get("progress_callback")
    
    if progress_callback:
        progress_callback("commit_forensics", 50)
    
    print(f"[5/10] 🕵️  Analyzing Team Effort & Git History...")
    return {"commit_analysis": analyze_commits(ctx.get("repo_path"))}

def node_quality_check(ctx):
    progress_callback = ctx.get("progress_callback")
    
    if progress_callback:
        progress_callback("quality_check", 60)
    
    print(f"[6/10] ⚖️  Assessing Code Quality & Documentation...")
    return {"quality_metrics": analyze_quality(ctx.get("repo_path"))}

def node_security_check(ctx):
    progress_callback = ctx.get("progress_callback")
    
    if progress_callback:
        progress_callback("security_scan", 70)
    
    print(f"[7/10] 🔐 Scanning for API Leaks & Secrets...")
    return {"security_report": scan_for_secrets(ctx.get("repo_path"))}

def node_forensic_analysis(ctx):
    progress_callback = ctx.get("progress_callback")
    
    if progress_callback:
        progress_callback("forensic_analysis", 80)
    
    print(f"[8/10] 🤖 Running Deep Forensics (AI & Plagiarism)...")
    repo_path = ctx.get("repo_path")
    providers = ctx.get("llm_providers", [])
    
    files = list_files(repo_path, ext_whitelist=[
        ".py", ".js", ".java", ".cpp", ".ts", ".go",
        ".jsx", ".tsx", ".c", ".h", ".cs", ".rs", ".php", 
        ".rb", ".swift", ".kt", ".scala", ".dart"
    ])
    
    file_contents = {}
    for f in files:
        content = read_file(f)
        if len(content) > 100: 
            file_contents[f] = {"content": content, "tokens": content.split()}

    # LLM Detection (Top 15 files) - OPTIMIZED: Parallel processing
    import concurrent.futures
    
    llm_results = {}
    target_files = sorted(file_contents.keys(), key=lambda k: len(file_contents[k]["content"]), reverse=True)[:15]
    
    def analyze_file_llm(file_path):
        # \"\"\"Analyze single file for LLM-generated code\"\"\"
        try:
            doc = file_contents[file_path]
            res = llm_origin_ensemble(doc, providers=providers)
            return file_path, res["score"]
        except Exception as e:
            print(f"      ⚠️  LLM analysis failed for {file_path}: {e}")
            return file_path, 0.0
    
    # Process up to 5 files in parallel (balance speed vs API rate limits)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(analyze_file_llm, f): f for f in target_files}
        for future in concurrent.futures.as_completed(futures):
            file_path, score = future.result()
            llm_results[file_path] = score

    # Internal Plagiarism (Top 20 files)
    plag_results = {}
    pool = sorted(file_contents.keys(), key=lambda k: len(file_contents[k]["content"]), reverse=True)[:20]
    for f_a in pool:
        best_score = 0.0
        best_file = None
        for f_b in pool:
            if f_a == f_b: continue
            sim = algorithmic_similarity(file_contents[f_a], file_contents[f_b])
            if sim["score"] > best_score:
                best_score = sim["score"]
                best_file = f_b
        plag_results[f_a] = {"score": best_score, "match": best_file}

    return {"llm_data": llm_results, "plag_data": plag_results}

def node_ai_judge(ctx):
    progress_callback = ctx.get("progress_callback")

    if progress_callback:
        progress_callback("ai_judge", 85)
    
    print(f"[9/13] 🧠 OpenAI (configured model) is reviewing the product logic...")
    api_key = ctx.get("openai_key") or os.environ.get("OPENAI_API_KEY")
    project_statement = ctx.get("project_statement")
    manual_archetype = ctx.get("manual_archetype")
    return {
        "ai_judgment": evaluate_product_logic(
            repo_path=ctx.get("repo_path"),
            api_key=api_key,
            project_statement=project_statement,
            manual_archetype=manual_archetype,
        )
    }

def node_test_coverage(ctx):
    progress_callback = ctx.get("progress_callback")
    
    if progress_callback:
        progress_callback("test_coverage", 87)
    
    print(f"[10/13] 🧪 Analyzing test coverage...")
    return {"test_coverage": analyze_test_coverage(ctx.get("repo_path"))}

def node_deployment_check(ctx):
    progress_callback = ctx.get("progress_callback")
    
    if progress_callback:
        progress_callback("deployment_check", 90)
    
    print(f"[11/13] 🚀 Verifying deployment status...")
    return {"deployment_status": verify_deployment(ctx.get("repo_path"), repo_url=ctx.get("repo_url"))}

def node_documentation_check(ctx):
    progress_callback = ctx.get("progress_callback")
    
    if progress_callback:
        progress_callback("documentation_check", 90)
    
    print(f"[12/14] 📚 Analyzing documentation completeness...")
    return {"documentation_analysis": analyze_documentation_completeness(ctx.get("repo_path"))}

def node_contributor_verification(ctx):
    progress_callback = ctx.get("progress_callback")
    
    if progress_callback:
        progress_callback("contributor_verification", 94)
    
    print(f"[13/14] 🔐 Verifying contributors against database team members...")
    # Get author stats from commit analysis
    comm = ctx.get("commit_analysis", {})
    author_stats = comm.get("author_stats", {})
    repo_url = ctx.get("repo_url")
    team_id = ctx.get("team_id")
    
    return {"contributor_verification": analyze_contributor_verification(author_stats, repo_url, team_id)}

def calculate_penalty_multiplier(
    fake_commit_ratio: float,
    quality_issue_ratio: float = 0.0,
    has_ai_bots: bool = False,
    ai_bot_share: float = 0.0,
) -> tuple:
    """
    Calculate penalty multipliers based on fake commits and quality issues.
    
    This function implements a graduated penalty system that treats fake commits
    (empty, repeated, suspicious) much more harshly than quality issues
    (dependencies, generated files).
    
    Fake Commit Penalties (Severe - Not Tolerable):
    - <10% fake: No penalty (1.0x multiplier)
    - 10-30% fake: 30% penalty (0.7x multiplier)
    - >30% fake: 60% penalty (0.4x multiplier)
    
    Quality Issue Penalties (Moderate - Tolerable but needs improvement):
    - <40% quality issues: No penalty (1.0x multiplier)
    - 40-70% quality issues: 15% penalty (0.85x multiplier)
    - >70% quality issues: 30% penalty (0.7x multiplier)
    
    Args:
        fake_commit_ratio: Percentage of truly fake commits (0-100 scale)
        quality_issue_ratio: Percentage of commits with quality issues (0-100 scale)
        has_ai_bots: Whether automated AI/bot contributors were detected
        ai_bot_share: Percentage of commits authored by automation/bot accounts (0-100)
        
    Returns:
        Tuple of (fake_penalty_multiplier, quality_penalty_multiplier)
        
    Examples:
        >>> calculate_penalty_multiplier(5.0, 20.0)
        (1.0, 1.0)  # Healthy - no penalties
        >>> calculate_penalty_multiplier(20.0, 50.0)
        (0.7, 0.85)  # Fake: 30% penalty, Quality: 15% penalty
        >>> calculate_penalty_multiplier(40.0, 80.0)
        (0.4, 0.7)  # Fake: 60% penalty, Quality: 30% penalty
    """
    # Handle invalid inputs by clamping to valid range
    if fake_commit_ratio is None or fake_commit_ratio != fake_commit_ratio:  # None or NaN
        print(f"⚠️ Warning: Invalid fake_commit_ratio (None or NaN), defaulting to 0")
        fake_commit_ratio = 0.0
    
    if quality_issue_ratio is None or quality_issue_ratio != quality_issue_ratio:
        quality_issue_ratio = 0.0
    
    # Clamp to valid range [0, 100]
    fake_commit_ratio = max(0.0, min(100.0, fake_commit_ratio))
    quality_issue_ratio = max(0.0, min(100.0, quality_issue_ratio))
    
    # Apply graduated penalty tiers for FAKE COMMITS (severe)
    if fake_commit_ratio < 10.0:
        fake_multiplier = 1.0  # Healthy - no penalty
    elif fake_commit_ratio < 30.0:
        fake_multiplier = 0.7  # Moderate - 30% penalty
    else:
        fake_multiplier = 0.4  # Critical - 60% penalty

    # Hard floor: AI/bot commit contributors are a critical repository-quality violation.
    # Ensure penalty is applied even when fake_commit_ratio is artificially low.
    if has_ai_bots:
        fake_multiplier = min(fake_multiplier, 0.4)

    # Heavy penalty tier: if bot/automation accounts dominate commits (>50%),
    # apply stricter reduction on affected dimensions.
    if ai_bot_share is None or ai_bot_share != ai_bot_share:
        ai_bot_share = 0.0
    ai_bot_share = max(0.0, min(100.0, ai_bot_share))
    if ai_bot_share > 50.0:
        fake_multiplier = min(fake_multiplier, 0.2)
    
    # Apply graduated penalty tiers for QUALITY ISSUES (moderate)
    if quality_issue_ratio < 40.0:
        quality_multiplier = 1.0  # Acceptable - no penalty
    elif quality_issue_ratio < 70.0:
        quality_multiplier = 0.85  # Needs improvement - 15% penalty
    else:
        quality_multiplier = 0.7  # Poor practice - 30% penalty
    
    return (fake_multiplier, quality_multiplier)

def calculate_team_size_adjustment(team_size: int, total_commits: int, total_relevance: float) -> tuple:
    """
    Calculate effort adjustment based on team size vs. output.
    
    This function rewards solo developers who complete everything alone,
    and penalizes teams of 3 with disproportionately low output per member.
    
    Team Size Adjustment Logic (Max Team Size: 3):
    - Solo (1 person): +10% bonus (1.1x multiplier) - did everything alone
    - Pair (2 people): No adjustment (1.0x multiplier)
    - Team of 3: Check output per person
      - Expected: 8+ commits/person OR 12+ relevance/person
      - Below expectation: -10% penalty (0.9x multiplier)
    
    Args:
        team_size: Number of team members (contributors, max 3)
        total_commits: Total number of commits in the repository
        total_relevance: Total relevance score from all contributors
        
    Returns:
        Tuple of (adjustment_multiplier, adjustment_reason)
        
    Examples:
        >>> calculate_team_size_adjustment(1, 25, 50.0)
        (1.1, "Solo developer bonus (+10%)")
        >>> calculate_team_size_adjustment(2, 30, 60.0)
        (1.0, "Pair team, no adjustment")
        >>> calculate_team_size_adjustment(3, 30, 70.0)
        (1.0, "Team of 3 output meets expectations")
        >>> calculate_team_size_adjustment(3, 18, 25.0)
        (0.9, "Team of 3 underperforming (6.0 commits/person, expected 8+)")
    """
    if team_size <= 0:
        return (1.0, "Invalid team size")
    
    commits_per_person = total_commits / team_size
    relevance_per_person = total_relevance / team_size
    
    # Solo developer bonus
    if team_size == 1:
        return (1.1, "Solo developer bonus (+10%)")
    
    # Pair (2 people) - no adjustment
    if team_size == 2:
        return (1.0, "Pair team, no adjustment")
    
    # Team of 3 - check if output is reasonable per person
    if team_size == 3:
        # Expected: at least 8 commits/person OR 12 relevance/person
        if commits_per_person >= 8 or relevance_per_person >= 12:
            return (1.0, "Team of 3 output meets expectations")
        else:
            reason = f"Team of 3 underperforming ({commits_per_person:.1f} commits/person, expected 8+)"
            return (0.9, reason)
    
    # If somehow team_size > 3 (data integrity issue), no penalty
    return (1.0, f"Team size {team_size} exceeds max (3), no adjustment")

def node_aggregator(ctx):
    progress_callback = ctx.get("progress_callback")
    
    if progress_callback:
        progress_callback("aggregation", 97)
    
    print(f"[14/14] 📊 Generating Final Evaluation Report...")
    
    # Inputs with type validation
    repo_path = ctx.get("repo_path")
    
    # Ensure all inputs are dicts (not lists or None)
    qual = ctx.get("quality_metrics") or {}
    if not isinstance(qual, dict):
        print(f"⚠️ Warning: quality_metrics is {type(qual)}, using empty dict")
        qual = {}
    
    comm = ctx.get("commit_analysis") or {}
    if not isinstance(comm, dict):
        print(f"⚠️ Warning: commit_analysis is {type(comm)}, using empty dict")
        comm = {}
    
    # [DEBUG] Log commit_analysis keys for branch tracking diagnosis
    print(f"[AGGREGATOR] commit_analysis keys: {list(comm.keys()) if isinstance(comm, dict) else 'NOT A DICT'}")
    if "branch_details" in comm:
        print(f"[AGGREGATOR] ✓ branch_details found with {len(comm.get('branch_details', {}))} branches")
    else:
        print(f"[AGGREGATOR] ✗ branch_details NOT FOUND in commit_analysis")
    
    sec = ctx.get("security_report") or {}
    if not isinstance(sec, dict):
        print(f"⚠️ Warning: security_report is {type(sec)}, using empty dict")
        sec = {}
    
    llm = ctx.get("llm_data") or {}
    if not isinstance(llm, dict):
        print(f"⚠️ Warning: llm_data is {type(llm)}, using empty dict")
        llm = {}
    
    plag = ctx.get("plag_data") or {}
    if not isinstance(plag, dict):
        print(f"⚠️ Warning: plag_data is {type(plag)}, using empty dict")
        plag = {}
    
    stack = ctx.get("tech_stack") or []
    if not isinstance(stack, list):
        print(f"⚠️ Warning: tech_stack is {type(stack)}, using empty list")
        stack = []
    
    judge = ctx.get("ai_judgment") or {}
    if not isinstance(judge, dict):
        print(f"⚠️ Warning: ai_judgment is {type(judge)}, using empty dict")
        judge = {}
    
    mat = ctx.get("maturity") or {}
    if not isinstance(mat, dict):
        print(f"⚠️ Warning: maturity is {type(mat)}, using empty dict")
        mat = {}
    
    struct = ctx.get("structure") or {}
    if not isinstance(struct, dict):
        print(f"⚠️ Warning: structure is {type(struct)}, using empty dict")
        struct = {}
    
    test_cov = ctx.get("test_coverage") or {}
    if not isinstance(test_cov, dict):
        print(f"⚠️ Warning: test_coverage is {type(test_cov)}, using empty dict")
        test_cov = {}
    
    deploy = ctx.get("deployment_status") or {}
    if not isinstance(deploy, dict):
        print(f"⚠️ Warning: deployment_status is {type(deploy)}, using empty dict")
        deploy = {}
    
    doc_analysis = ctx.get("documentation_analysis") or {}
    if not isinstance(doc_analysis, dict):
        print(f"⚠️ Warning: documentation_analysis is {type(doc_analysis)}, using empty dict")
        doc_analysis = {}
    
    contrib_verify = ctx.get("contributor_verification") or {}
    if not isinstance(contrib_verify, dict):
        print(f"⚠️ Warning: contributor_verification is {type(contrib_verify)}, using empty dict")
        contrib_verify = {}
    
    # Print contributor verification summary
    if contrib_verify:
        api_status = contrib_verify.get("api_status", {})
        verification = contrib_verify.get("verification", {})
        
        if api_status.get("success"):
            collab_count = contrib_verify.get("collaborator_count", 0)
            verified = verification.get("verified_authors", 0)
            unverified = len(verification.get("unauthorized_authors", []))
            
            if unverified > 0:
                severity = verification.get("severity", "none")
                print(f"      ✅ Contributor Verification Complete: {verified} verified, {unverified} unauthorized ({severity})")
            else:
                print(f"      ✅ Contributor Verification Complete: All {verified} contributors verified")
        elif verification.get("verification_skipped"):
            reason = verification.get("reason", "Unknown")
            print(f"      ⏭️  Contributor Verification Skipped: {reason}")
        else:
            error = api_status.get("error", "Unknown error")
            print(f"      ⚠️  Contributor Verification Failed: {error}")
    
    # --- Generate Tree (For Output) ---
    repo_tree = "Tree generation skipped (missing repo_path)" 
    if repo_path and os.path.exists(repo_path):
        try:
            repo_tree = generate_tree_structure(repo_path)
        except Exception as e:
            print(f"⚠️ Tree generation failed: {e}")
            repo_tree = f"Tree generation failed: {str(e)}"

    # --- Process Files ---
    detailed_files = []
    viz_files = []
    all_files = set(llm.keys()) | set(plag.keys())
    
    for fpath in all_files:
        s_ai = llm.get(fpath, 0.0)
        s_plag = plag.get(fpath, {}).get("score", 0.0)
        risk = ((s_ai * 0.6) + (s_plag * 0.4)) * 100
        
        viz_files.append({"path": fpath, "S_llm": s_ai, "S_alg": s_plag, "S_cross": max(s_ai, s_plag)})
        
        if risk > 15: 
            match_path = plag.get(fpath, {}).get("match", "") or ""
            detailed_files.append({
                "name": os.path.basename(fpath),
                "ai_pct": s_ai * 100,
                "plag_pct": s_plag * 100,
                "risk": risk,
                "match": os.path.basename(match_path) if match_path else "None"
            })
            
    detailed_files.sort(key=lambda x: x['risk'], reverse=True)
    
    # Calculate overall AI percentage from all files (not just risky ones)
    all_ai_scores = [llm.get(f, 0.0) * 100 for f in llm.keys()]
    overall_ai_percentage = round(sum(all_ai_scores) / len(all_ai_scores), 2) if all_ai_scores else 0.0
    top_ai = max(all_ai_scores) if all_ai_scores else 0.0
    
    # --- Check for empty repository ---
    total_commits = comm.get("total_commits", 0)
    total_relevance = comm.get("total_relevance", 0)
    
    # Get fake commit data
    fake_commit_ratio = comm.get("fake_commit_ratio", 0) / 100.0  # Convert to 0-1
    real_commit_count = comm.get("real_commit_count", total_commits)
    
    # Check if repo is empty or has minimal/no meaningful content
    # Consider repo empty/minimal if:
    # 1. Zero commits, OR
    # 2. Very few commits (<= 2) AND very low relevance score (< 5)
    is_empty_or_minimal = (
        total_commits == 0 or 
        (total_commits <= 2 and total_relevance < 5)
    )
    
    if is_empty_or_minimal:
        print(f"⚠️  Empty/minimal repository detected ({total_commits} commits, {total_relevance} relevance). Setting all scores to 0.")
        scores = {
            "originality": 0,
            "quality": 0,
            "security": 0,
            "effort": 0,
            "implementation": 0,
            "engineering": 0,
            "organization": 0,
            "documentation": 0
        }
        # For empty repos, base scores are also 0
        base_scores = scores.copy()
        penalty_multiplier = 1.0
        commit_health = "Healthy"
        team_size = 0
        team_adjustment_multiplier = 1.0
        team_adjustment_reason = "N/A"
        days_inactive = 0
        inactive_penalty = 1.0
        outsourcing_penalty = 1.0
        has_outsourced_work = False
        outsourcing_severity = "none"
    else:
        # --- Calculate Base Scores (before penalties) ---
        # Use 0 as default when data is missing (no artificial inflation)
        impl_score = judge.get("implementation_score", 0)  # 0 if AI fails
        
        # Calculate Effort based on Relevance Score (capped at 100)
        # Target: 50 relevance points = 100 score (approx 20 meaningful commits)
        relevance = comm.get("total_relevance", 0)
        effort_base = min(100, relevance * 2)
        
        # Apply team size adjustment to effort score
        author_stats = comm.get("author_stats", {})
        team_size = len(author_stats)
        total_commits = comm.get("total_commits", 0)
        
        team_adjustment_multiplier, team_adjustment_reason = calculate_team_size_adjustment(
            team_size, 
            total_commits, 
            relevance
        )
        
        # Apply team size adjustment to effort
        effort_base = round(effort_base * team_adjustment_multiplier, 1)
        effort_base = min(100, effort_base)
        
        # Log team size adjustment if applied
        if team_adjustment_multiplier != 1.0:
            if team_adjustment_multiplier > 1.0:
                print(f"✅ Team Size Bonus Applied:")
                print(f"      Team Size: {team_size} member(s)")
                print(f"      Reason: {team_adjustment_reason}")
                print(f"      Multiplier: {team_adjustment_multiplier}x")
            else:
                print(f"⚠️  Team Size Penalty Applied:")
                print(f"      Team Size: {team_size} members")
                print(f"      Output: {total_commits} commits, {relevance:.1f} relevance")
                print(f"      Reason: {team_adjustment_reason}")
                print(f"      Multiplier: {team_adjustment_multiplier}x")
        
        # Get quality detection data
        fake_commit_ratio_raw = comm.get("fake_commit_ratio", 0)  # 0-100 scale (truly fake commits)
        quality_issue_ratio_raw = comm.get("quality_issue_ratio", 0)  # 0-100 scale (tolerable issues)
        commit_health = comm.get("commit_health", "Healthy")
        ai_bot_detection = comm.get("ai_bot_detection", {}) if isinstance(comm, dict) else {}
        has_ai_bots = False
        ai_bot_share = 0.0
        if isinstance(ai_bot_detection, dict):
            has_ai_bots = bool(
                ai_bot_detection.get("has_ai_bots")
                or (ai_bot_detection.get("ai_bot_contributors") or [])
            )
            ai_bot_contributors = ai_bot_detection.get("ai_bot_contributors", []) or []
            if isinstance(ai_bot_contributors, list):
                ai_bot_share = sum(
                    float(bot.get("share", 0) or 0)
                    for bot in ai_bot_contributors
                    if isinstance(bot, dict)
                )
        ai_bot_share = max(0.0, min(100.0, ai_bot_share))
        
        # Calculate repository quality penalty multipliers (separate for fake vs quality issues)
        fake_multiplier, quality_multiplier = calculate_penalty_multiplier(
            fake_commit_ratio_raw, 
            quality_issue_ratio_raw,
            has_ai_bots=has_ai_bots,
            ai_bot_share=ai_bot_share,
        )
        
        # Combined repository quality penalty (multiply both)
        repo_quality_multiplier = fake_multiplier * quality_multiplier
        
        # Calculate inactivity penalty (14 days without commits = 14% penalty)
        inactive_penalty = 1.0
        days_inactive = 0
        last_commit_date_str = comm.get("last_commit_date")
        if last_commit_date_str:
            try:
                # Handle ISO format string with or without timezone
                if last_commit_date_str.endswith('Z'):
                    last_commit_date_str = last_commit_date_str[:-1] + '+00:00'
                last_commit = datetime.fromisoformat(last_commit_date_str)
                # Ensure timezone awareness matches
                now = datetime.now(last_commit.tzinfo) if last_commit.tzinfo else datetime.now()
                days_inactive = (now - last_commit).days
                
                if days_inactive >= 14:
                    inactive_penalty = 0.86  # 14% score reduction
            except Exception as e:
                print(f"⚠️ Error parsing last_commit_date '{last_commit_date_str}': {e}")
        
        # Get contributor verification penalty
        outsourcing_penalty = contrib_verify.get("penalty_recommended", 1.0)
        verification_result = contrib_verify.get("verification", {})
        has_outsourced_work = verification_result.get("has_outsourced_work", False)
        outsourcing_severity = verification_result.get("severity", "none")
        
        # Combined penalty (repository quality + inactivity + outsourcing)
        total_penalty_multiplier = repo_quality_multiplier * inactive_penalty * outsourcing_penalty
        
        # Store base scores (before penalties)
        base_scores = {
            "originality": max(0, 100 - top_ai),
            "quality": qual.get("maintainability_index", 0),  # 0 if no analysis done
            "security": sec.get("score", 0),  # 0 if no scan done
            "effort": effort_base,
            "implementation": impl_score,
            "engineering": mat.get("score", 0),  # 0 if no devops found
            "organization": struct.get("organization_score", 0),  # 0 if not analyzed
            "documentation": doc_analysis.get("documentation_score", 0),  # Enhanced documentation score
            "test_coverage": test_cov.get("test_coverage_score", 0),  # NEW: Test coverage
            "deployment": deploy.get("deployment_score", 0)  # NEW: Deployment verification
        }
        
        # Apply penalties to affected dimensions
        # Affected: implementation, quality, organization, effort
        # Protected: originality, security, engineering, documentation, test_coverage, deployment
        scores = {
            "originality": base_scores["originality"],  # Protected
            "quality": round(base_scores["quality"] * total_penalty_multiplier, 1),  # Affected
            "security": base_scores["security"],  # Protected
            "effort": round(base_scores["effort"] * total_penalty_multiplier, 1),  # Affected
            "implementation": round(base_scores["implementation"] * total_penalty_multiplier, 1),  # Affected
            "engineering": base_scores["engineering"],  # Protected
            "organization": round(base_scores["organization"] * total_penalty_multiplier, 1),  # Affected
            "documentation": base_scores["documentation"],  # Protected
            "test_coverage": base_scores["test_coverage"],  # Protected (NEW)
            "deployment": base_scores["deployment"]  # Protected (NEW)
        }
        
        # Store penalty_multiplier for return value (used at line 755)
        penalty_multiplier = total_penalty_multiplier
        
        # Log penalty application if applied
        if fake_multiplier < 1.0 or quality_multiplier < 1.0 or inactive_penalty < 1.0 or outsourcing_penalty < 1.0:
            if fake_multiplier < 1.0:
                print(f"⚠️  Fake Commit Penalty Applied (SEVERE):")
                print(f"      Health: {commit_health}")
                print(f"      Fake Commits: {fake_commit_ratio_raw}% (empty, repeated, suspicious)")
                if has_ai_bots:
                    print(f"      AI/Bot Contributors: DETECTED ({ai_bot_share:.1f}% share)")
                    if ai_bot_share > 50.0:
                        print(f"      Heavy Policy Penalty: Applied (>50% automation commits)")
                print(f"      Fake Penalty Multiplier: {fake_multiplier}x")
            
            if quality_multiplier < 1.0:
                print(f"⚠️  Quality Issue Penalty Applied (MODERATE):")
                print(f"      Quality Issues: {quality_issue_ratio_raw}% (dependencies, generated files)")
                print(f"      Quality Penalty Multiplier: {quality_multiplier}x")
            
            if inactive_penalty < 1.0:
                print(f"⚠️  Inactivity Penalty Applied:")
                print(f"      Days Inactive: {days_inactive} days")
                print(f"      Inactive Penalty Multiplier: {inactive_penalty}x")
            
            if outsourcing_penalty < 1.0:
                print(f"⚠️  Outsourcing Penalty Applied ({outsourcing_severity.upper()}):")
                unauth_authors = verification_result.get("unauthorized_authors", [])
                unauth_ratio = verification_result.get("unauthorized_commit_ratio", 0)
                print(f"      Unauthorized Contributors: {len(unauth_authors)}")
                print(f"      Unauthorized Commits: {unauth_ratio}%")
                if unauth_authors:
                    top_unauth = unauth_authors[:3]  # Show top 3
                    for ua in top_unauth:
                        print(f"        - {ua['name']}: {ua['commits']} commits ({ua['share']}%)")
                print(f"      Outsourcing Penalty Multiplier: {outsourcing_penalty}x")
                
            print(f"      Total Multiplier: {total_penalty_multiplier}x")
            print(f"      Affected Dimensions: implementation, quality, organization, effort")

    # Apply a hard penalty for docs-only repositories (README-only, no code)
    # Only apply this penalty if we actually checked the filesystem AND found no code
    # Don't apply if forensic analysis simply didn't run or found no risky files
    def _is_docs_only_repo(path: str) -> bool:
        if not path or not os.path.exists(path):
            return False

        code_exts = [
            ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".cpp", ".c",
            ".cs", ".rs", ".php", ".rb", ".kt", ".swift", ".dart"
        ]
        code_files = list_files(path, ext_whitelist=code_exts)
        if code_files:
            return False

        trivial_names = {
            "readme", "readme.md", "readme.txt",
            "license", "license.md", "license.txt",
            ".gitignore", ".gitattributes", ".editorconfig",
            "notice", "notice.txt"
        }

        exclude_dirs = {
            ".git", ".github", "node_modules", "venv", ".venv", "env", "dist",
            "build", "target", "bin", "obj", "__pycache__", "coverage"
        }

        total_files = 0
        non_trivial = 0

        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith(".")]
            for name in files:
                if name.startswith("."):
                    continue
                total_files += 1
                lower = name.lower()
                if lower in trivial_names or lower.endswith((".md", ".txt")):
                    continue
                non_trivial += 1

        return total_files > 0 and non_trivial == 0

    # Only apply docs-only penalty if we have very few commits AND no code files
    # Increased threshold from 5 to 10 commits to catch more minimal repos
    if total_commits < 10 and _is_docs_only_repo(repo_path):
        print(f"⚠️  Docs-only repository detected ({total_commits} commits, no code files). Applying minimal scores.")
        scores = {
            "originality": 5,
            "quality": 5,
            "security": 5,
            "effort": 0,
            "implementation": 5,
            "engineering": 5,
            "organization": 5,
            "documentation": 10
        }
        # For docs-only repos, base scores are the same (no penalty applied)
        base_scores = scores.copy()
        penalty_multiplier = 1.0
        commit_health = "Healthy"
        team_size = 0
        team_adjustment_multiplier = 1.0
        team_adjustment_reason = "N/A"
        days_inactive = 0
        inactive_penalty = 1.0
        outsourcing_penalty = 1.0
        has_outsourced_work = False
        outsourcing_severity = "none"
    
    # --- Viz ---
    output_dir = ctx.get("output_dir") or "."
    if not output_dir:
        output_dir = "."
    viz_path = os.path.join(output_dir, "scorecard.png")
    try:
        generate_dashboard(scores, viz_files, viz_path)
    except Exception as e:
        print(f"⚠️ Dashboard generation failed: {e}")
        viz_path = "N/A"

    return {
        "final_report": {
            "repo": ctx.get("repo_url"),
            "stack": stack,
            "scores": scores,
            "base_scores": base_scores,  # Pre-penalty scores
            "penalty_info": {  # Penalty metadata
                "fake_commit_ratio": comm.get("fake_commit_ratio", 0),
                "commit_health": commit_health,
                "has_ai_bots": has_ai_bots if not is_empty_or_minimal else False,
                "ai_bot_share": round(ai_bot_share, 1) if not is_empty_or_minimal else 0.0,
                "heavy_ai_bot_penalty": (ai_bot_share > 50.0) if not is_empty_or_minimal else False,
                "penalty_multiplier": penalty_multiplier if not is_empty_or_minimal else 1.0,
                "days_inactive": days_inactive if not is_empty_or_minimal else 0,
                "inactive_penalty": inactive_penalty if not is_empty_or_minimal else 1.0,
                "team_size": team_size if not is_empty_or_minimal else 0,
                "team_adjustment_multiplier": team_adjustment_multiplier if not is_empty_or_minimal else 1.0,
                "team_adjustment_reason": team_adjustment_reason if not is_empty_or_minimal else "N/A",
                "outsourcing_penalty": outsourcing_penalty if not is_empty_or_minimal else 1.0,
                "outsourcing_severity": outsourcing_severity if not is_empty_or_minimal else "none",
                "has_outsourced_work": has_outsourced_work if not is_empty_or_minimal else False,
                "penalty_version": "v2.4"  # Updated version
            },
            "team": comm.get("author_stats", {}),
            "total_commits": comm.get("total_commits", 0),
            "files": detailed_files,
            "llm_detection": {"overall_percentage": overall_ai_percentage},
            "security": sec,
            "judge": judge,
            "maturity": mat,
            "commit_details": comm,
            "structure": struct,
            "test_coverage": test_cov,  # NEW: Test coverage analysis
            "deployment_status": deploy,  # NEW: Deployment verification
            "documentation_analysis": doc_analysis,  # NEW: Documentation completeness
            "contributor_verification": contrib_verify,  # NEW: Contributor verification
            "project_statement": ctx.get("project_statement"),  # Project context for reports
            "repo_tree": repo_tree,
            "viz": viz_path
        }
    }

# ==========================================
# 2. Build Pipeline
# ==========================================

def build_pipeline(repo_url, output_dir, providers, openai_key, progress_callback=None, team_id=None, project_statement=None, manual_archetype=None):
    g = SimpleLangGraph()
    
    g.add_node("clone", node_clone_repo)
    g.add_node("stack", node_stack_id)
    g.add_node("structure", node_structure_analysis)
    g.add_node("maturity", node_maturity_check)
    g.add_node("commits", node_commit_forensics)
    g.add_node("quality", node_quality_check)
    g.add_node("security", node_security_check)
    g.add_node("forensics", node_forensic_analysis)
    g.add_node("judge", node_ai_judge)
    g.add_node("test_coverage", node_test_coverage)  # NEW
    g.add_node("deployment", node_deployment_check)  # NEW
    g.add_node("documentation", node_documentation_check)  # NEW
    g.add_node("contributor_verification", node_contributor_verification)  # NEW
    g.add_node("aggregator", node_aggregator)
    
    # Edges (Parallel Execution)
    g.add_edge("clone", "stack")
    g.add_edge("clone", "structure")
    g.add_edge("clone", "maturity")
    g.add_edge("clone", "commits")
    g.add_edge("clone", "quality")
    g.add_edge("clone", "security")
    g.add_edge("clone", "forensics")
    g.add_edge("clone", "judge")
    g.add_edge("clone", "test_coverage")  # NEW
    g.add_edge("clone", "deployment")  # NEW
    g.add_edge("clone", "documentation")  # NEW
    
    # Contributor verification depends on commit forensics (needs author_stats)
    g.add_edge("commits", "contributor_verification")  # NEW
    
    # Edges (Aggregation)
    g.add_edge("stack", "aggregator")
    g.add_edge("structure", "aggregator")
    g.add_edge("maturity", "aggregator")
    g.add_edge("commits", "aggregator")
    g.add_edge("quality", "aggregator")
    g.add_edge("security", "aggregator")
    g.add_edge("forensics", "aggregator")
    g.add_edge("judge", "aggregator")
    g.add_edge("test_coverage", "aggregator")  # NEW
    g.add_edge("deployment", "aggregator")  # NEW
    g.add_edge("documentation", "aggregator")  # NEW
    g.add_edge("contributor_verification", "aggregator")  # NEW
    
    return g.run({
        "repo_url": repo_url,
        "output_dir": output_dir,
        "llm_providers": providers,
        "openai_key": openai_key,
        "progress_callback": progress_callback,
        "team_id": str(team_id) if team_id else None,
        "project_statement": project_statement,
        "manual_archetype": manual_archetype
    })

# ==========================================
# 3. CSV Export Logic (WITH STRUCTURE FILE)
# ==========================================

def format_file_extensions(ext_string):
    if not ext_string: return "Unknown"
    
    mapping = {
        "py": "Python", "js": "JS", "ts": "TypeScript", 
        "jsx": "React", "tsx": "React", "css": "CSS", 
        "html": "HTML", "json": "Config", "md": "Docs", 
        "txt": "Text", "jpg": "Images", "png": "Images", 
        "java": "Java", "cpp": "C++"
    }
    
    parts = ext_string.split(", ")
    clean_types = set()
    for p in parts:
        ext = p.split(" ")[0]
        readable = mapping.get(ext, ext.upper())
        clean_types.add(readable)
        
    return ", ".join(sorted(clean_types))

def clean_winner_text(text):
    if not text or "None" in text: return "None"
    if "Led" in text:
        parts = text.split("Led ")
        name = parts[0].strip(" (")
        count = parts[1].strip(")")
        return f"{name} (Top for {count})"
    return text

def save_csv_results(output_dir, team_name, data):
    # Validate output_dir
    if not output_dir:
        output_dir = "."
    
    scores = data.get("scores", {})
    judge = data.get("judge", {})
    mat = data.get("maturity", {})
    struct = data.get("structure", {})
    comm = data.get("commit_details", {})
    sec = data.get("security", {})
    
    def clean_text(text):
        return str(text).replace("\n", " | ").replace("\r", "").strip()

    # --- SAVE REPO STRUCTURE TO TEXT FILE ---
    tree_content = data.get("repo_tree", "Tree generation failed.")
    structure_file = os.path.join(output_dir, "repository_structure.txt")
    try:
        with open(structure_file, "w", encoding="utf-8") as f:
            f.write(tree_content)
    except Exception as e:
        print(f"⚠️ Failed to save structure file: {e}")

    # --- PROCESS AUTHOR STATS ---
    author_stats = comm.get("author_stats", {})
    consistency = comm.get("consistency_stats", {})
    
    sorted_authors = sorted(author_stats.items(), key=lambda x: x[1]['commits'], reverse=True)
    
    breakdown_parts = []
    for name, stats in sorted_authors:
        commits = stats.get('commits', 0)
        days = stats.get('active_days_count', 0)
        raw_files = stats.get('top_file_types', '')
        readable_files = format_file_extensions(raw_files)
        
        part = f"{name}: {commits} commits (Active {days}d). Focus: {readable_files}"
        breakdown_parts.append(part)
        
    contribution_string = " | ".join(breakdown_parts)

    score_row = {
        # --- IDENTITY ---
        "Team_Name": team_name,
        "Repo_URL": data.get("repo"),
        "Tech_Stack": ", ".join(data.get("stack", [])),
        
        # --- SCORES (UPDATED WITH NEW DIMENSIONS) ---
        "TOTAL_SCORE": round(sum([
            scores.get('originality', 0) * 0.15,
            scores.get('implementation', 0) * 0.20,
            scores.get('engineering', 0) * 0.15,
            scores.get('security', 0) * 0.10,
            scores.get('quality', 0) * 0.10,
            scores.get('test_coverage', 0) * 0.10,  # NEW: 10%
            scores.get('documentation', 0) * 0.05,  # Updated weight
            scores.get('deployment', 0) * 0.05,  # NEW: 5%
            scores.get('effort', 0) * 0.10  # Reduced from 20% to 10%
        ]), 1),
        
        "Implementation": round(scores.get('implementation', 0), 1),
        "Originality": round(scores.get('originality', 0), 1),
        "Engineering": round(scores.get('engineering', 0), 1),
        "Code_Quality": round(scores.get('quality', 0), 1),
        "Security": round(scores.get('security', 0), 1),
        "Test_Coverage": round(scores.get('test_coverage', 0), 1),  # NEW
        "Documentation": round(scores.get('documentation', 0), 1),
        "Deployment": round(scores.get('deployment', 0), 1),  # NEW
        "Organization": round(scores.get('organization', 0), 1),
        "Effort": round(scores.get('effort', 0), 1),
        "Mean_Relevance": round(comm.get("total_relevance", 0) / max(1, comm.get("total_commits", 1)), 2),

        # --- AI FEEDBACK ---
        "AI_Pros": clean_text(judge.get("positive_feedback", "")),
        "AI_Cons": clean_text(judge.get("constructive_feedback", "")),
        
        # --- FORENSICS & ACTIVITY ---
        "Total_Commits": comm.get("total_commits", 0),
        "Real_Commits": comm.get("real_commit_count", comm.get("total_commits", 0)),
        "Fake_Commits": comm.get("fake_commit_count", 0),
        "Fake_Commit_Ratio": comm.get("fake_commit_ratio", 0),
        "Real_Additions": comm.get("total_real_additions", 0),
        "Fake_Additions": comm.get("total_fake_additions", 0),
        "Inflation_Ratio": comm.get("inflation_ratio", 1.0),
        "Commit_Health": comm.get("commit_health", "Healthy"),
        "Days_Inactive": data.get("penalty_info", {}).get("days_inactive", 0),
        "Branch_Count": comm.get("branch_count", 0),
        "Branches": ", ".join(comm.get("branches", [])),
        "Dummy_Commits": comm.get("dummy_commits", 0),
        "Team_Size": len(author_stats),
        "Contribution_Summary": contribution_string,
        
        # --- CONTRIBUTOR VERIFICATION ---
        "Verified_Contributors": data.get("contributor_verification", {}).get("verification", {}).get("verified_authors", 0),
        "Unauthorized_Contributors": data.get("contributor_verification", {}).get("verification", {}).get("unauthorized_commits", 0),
        "Outsourcing_Severity": data.get("contributor_verification", {}).get("verification", {}).get("severity", "none"),
        "Has_Outsourced_Work": data.get("contributor_verification", {}).get("verification", {}).get("has_outsourced_work", False),
        
        # --- PERIOD WINNERS ---
        "Top_Daily": clean_winner_text(consistency.get("top_daily", "N/A")),
        "Top_Weekly": clean_winner_text(consistency.get("top_weekly", "N/A")),
        "Top_Monthly": clean_winner_text(consistency.get("top_monthly", "N/A")),

        # --- ENGINEERING DETAILS ---
        "Architecture": struct.get("architecture", "Unknown"),
        "DevOps_Tools": ", ".join(mat.get("devops_tools", [])),
        "Sec_Leaks": sec.get("leak_count", 0),
        "Is_Deployable": mat.get("is_deployable", False),
        
        # --- LINKS ---
        "Scorecard_Image": os.path.abspath(os.path.join(output_dir, "scorecard.png")),
        "Structure_File": os.path.abspath(structure_file) # <--- NEW LINK
    }
    
    scorecard_path = os.path.join(output_dir, "scorecard.csv")
    with open(scorecard_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=score_row.keys())
        writer.writeheader()
        writer.writerow(score_row)

    # Save Files Analysis
    files = data.get("files", [])
    if files:
        files_path = os.path.join(output_dir, "files_analysis.csv")
        file_keys = ["filename", "risk", "ai_pct", "plag_pct", "match"]
        with open(files_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=file_keys)
            writer.writeheader()
            writer.writerows(files)

    return score_row

# ==========================================
# 4. Universal Batch Input Parser
# ==========================================

def parse_input_file(file_path):
    repos = []
    ext = os.path.splitext(file_path)[1].lower()
    
    print(f"📂 Parsing input file: {file_path} ({ext})")
    
    try:
        # --- EXCEL FORMAT ---
        if ext in ['.xlsx', '.xls']:
            try:
                import pandas as pd
            except ImportError:
                print("❌ Missing dependency: pandas. Please run 'pip install pandas openpyxl'")
                return []
            
            df = pd.read_excel(file_path)
            df.columns = df.columns.str.strip().str.lower()
            data = df.to_dict(orient='records')
            
            for row in data:
                url = row.get('repo url') or row.get('url') or row.get('repo')
                name = row.get('team name') or row.get('name') or row.get('team') or f"Team-{len(repos)+1}"
                if url and pd.notna(url) and str(url).strip().startswith('http'):
                    repos.append({"name": str(name).strip(), "url": str(url).strip()})

        # --- JSON FORMAT ---
        elif ext == '.json':
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    for entry in data:
                        clean = {k.strip().lower(): v for k, v in entry.items()}
                        url = clean.get('repo url') or clean.get('url') or clean.get('repo')
                        name = clean.get('team name') or clean.get('name') or clean.get('team') or "Unknown"
                        if url:
                            repos.append({"name": name, "url": url.strip()})
        
        # --- CSV / TEXT FORMAT ---
        else:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                sample = f.read(1024)
                f.seek(0)
                has_header = csv.Sniffer().has_header(sample) if ',' in sample else False
                
                if has_header or ',' in sample:
                    reader = csv.DictReader(f)
                    for row in reader:
                        clean = {k.strip().lower(): v.strip() for k, v in row.items()}
                        url = clean.get('repo url') or clean.get('url') or clean.get('repo')
                        name = clean.get('team name') or clean.get('name') or clean.get('team') or f"Team-{len(repos)+1}"
                        if url:
                            repos.append({"name": name, "url": url})
                else:
                    print("ℹ️  Treating file as raw URL list.")
                    for line in f:
                        line = line.strip()
                        if line and line.startswith("http"):
                            repos.append({"name": f"Team-{len(repos)+1}", "url": line})

    except Exception as e:
        print(f"❌ Error parsing input file: {e}")
        return []

    return repos

# ==========================================
# 5. Batch Runner (SAFE SAVE)
# ==========================================

def run_batch_mode(file_path, output_dir, providers, openai_key):
    repos = parse_input_file(file_path)
    
    if not repos:
        print("❌ No valid repositories found in input file.")
        return

    print(f"📋 Found {len(repos)} teams to evaluate.\n")
    
    results = []
    failed = []
    
    for i, team in enumerate(repos):
        team_name = team['name']
        url = team['url']
        
        print(f"\n{'='*60}")
        print(f"⏳ Processing {i+1}/{len(repos)}: {team_name}")
        print(f"{'='*60}")
        
        safe_name = "".join([c if c.isalnum() else "_" for c in team_name])
        team_out_dir = os.path.join(output_dir, safe_name)
        os.makedirs(team_out_dir, exist_ok=True)
        
        try:
            res = build_pipeline(url, team_out_dir, providers, openai_key)
            data = res.get("final_report", {})
            score_row = save_csv_results(team_out_dir, team_name, data)
            results.append(score_row)
            print(f"✅ Finished {team_name} (Score: {score_row['TOTAL_SCORE']})")
        except Exception as e:
            print(f"❌ Failed {team_name}: {e}")
            failed.append(team_name)

    if results:
        keys = list(results[0].keys())
        results.sort(key=lambda x: float(x['TOTAL_SCORE']), reverse=True)
        for idx, r in enumerate(results):
            r["Rank"] = idx + 1
        if "Rank" not in keys: keys.insert(0, "Rank")

        # --- SAFE SAVE LOGIC ---
        lb_filename = "LEADERBOARD.csv"
        lb_path = os.path.join(output_dir, lb_filename)
        
        counter = 1
        while True:
            try:
                # Check permission by opening in append mode
                with open(lb_path, "a", newline="", encoding="utf-8-sig"): pass
                
                # Write file
                with open(lb_path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=keys)
                    writer.writeheader()
                    writer.writerows(results)
                print(f"\n🎉 Batch Complete! Leaderboard saved to: {os.path.abspath(lb_path)}")
                break
            except PermissionError:
                print(f"⚠️  File '{lb_filename}' is open. Saving to new file...")
                lb_filename = f"LEADERBOARD_{counter}.csv"
                lb_path = os.path.join(output_dir, lb_filename)
                counter += 1
            except Exception as e:
                print(f"❌ Critical Error saving leaderboard: {e}")
                break

    if failed:
        print(f"⚠️  Failed Teams: {', '.join(failed)}")

# ==========================================
# 6. Helpers & Printer
# ==========================================

def print_row(col1, col2, col3="", col4=""):
    print(f"  {col1:<25} | {col2:<15} | {col3:<15} | {col4}")

def rate(val, high=80, low=50):
    return "✅ Excellent" if val > high else "⚠️ Needs Work" if val > low else "❌ Critical"

def print_single_report(data):
    scores = data.get("scores", {})
    judge = data.get("judge", {})
    mat = data.get("maturity", {})
    struct = data.get("structure", {})
    comm = data.get("commit_details", {})
    consistency = comm.get("consistency_stats", {})
    
    print("\n" * 2)
    print("="*80)
    print(f"       🏆  HACKATHON EVALUATION REPORT  🏆")
    print("="*80)
    print(f"\n[1] PROJECT OVERVIEW")
    print(f"  📂 Repository:       {data.get('repo')}")
    print(f"  🤖 Project Name:     {judge.get('project_name', 'Unknown')}")
    print(f"  🛠️  Tech Stack:       {', '.join(data.get('stack', []))}")

    print(f"\n[2] JUDGE'S SCORECARD (0-100)")
    print(f"  {'METRIC':<20} {'SCORE':<10} {'STATUS'}")
    print(f"  {'-'*20} {'-'*10} {'-'*20}")
    print(f"  Originality         {scores.get('originality', 0):<10.1f} {rate(scores.get('originality', 0), 70, 40)}")
    print(f"  Implementation      {scores.get('implementation', 0):<10.1f} {rate(scores.get('implementation', 0), 80, 50)}")
    print(f"  Engineering         {scores.get('engineering', 0):<10.1f} {rate(scores.get('engineering', 0), 60, 30)}")
    print(f"  Structure/Org       {scores.get('organization', 0):<10.1f} {rate(scores.get('organization', 0), 80, 60)}")
    print(f"  Code Quality        {scores.get('quality', 0):<10.1f} {rate(scores.get('quality', 0), 60, 40)}")
    print(f"  Security            {scores.get('security', 0):<10.1f} {rate(scores.get('security', 0), 99, 80)}")

    if judge.get("project_name") != "Unknown":
        print(f"\n[3] 🧠 AI JUDGE FEEDBACK")
        print(f"  👍 Pros:  \"{judge.get('positive_feedback')}\"")
        print(f"  💡 Cons:  \"{judge.get('constructive_feedback')}\"")
        print(f"  ⚖️  Verdict: {judge.get('verdict')}")

    print(f"\n[4] 🏗️  ARCHITECTURE & ORGANIZATION")
    print(f"  🏛️  Detected Pattern:  {struct.get('architecture', 'Unknown')}")
    depth = struct.get("max_depth", 0)
    print(f"  ✅ Good Directory Organization ({depth} levels).")

    print(f"\n[5] 🚀 ENGINEERING MATURITY")
    print(f"  📦 Deployable?       {'✅ Yes (Docker/Cloud)' if mat.get('is_deployable') else '❌ No (Local only)'}")
    print(f"  🧪 Test Suite:       {mat.get('test_files', 0)} files / {mat.get('test_lines', 0)} lines")

    sec = data.get("security", {})
    if sec.get("leak_count", 0) > 0:
        print(f"\n[6] 🔐 SECURITY ALERTS")
        print(f"  ⚠️  Found {sec['leak_count']} secret leaks!")
    else:
        print(f"\n[6] 🔐 SECURITY STATUS: ✅ Safe")

    print(f"\n[7] 👥 DETAILED TEAM ACTIVITY")
    print(f"  📅 Top Daily Contributor:   {clean_winner_text(consistency.get('top_daily', 'N/A'))}")
    print(f"  🌿 Branches Detected:       {comm.get('branch_count', 0)} ({', '.join(comm.get('branches', [])[:3])}...)")
    
    if comm.get("dummy_commits", 0) > 0:
        print(f"  ⚠️  WARNING: {comm['dummy_commits']} dummy/empty commits detected!")
        
    author_stats = comm.get("author_stats", {})
    if author_stats:
        sorted_team = sorted(author_stats.items(), key=lambda x: x[1]['commits'], reverse=True)
        print(f"\n  {'AUTHOR':<20} | {'COMMITS':<8} | {'ACTIVE':<12} | {'FOCUS AREA'}")
        print(f"  {'-'*20} | {'-'*8} | {'-'*12} | {'-'*20}")
        for name, stats in sorted_team:
             files = format_file_extensions(stats.get('top_file_types', ''))
             print(f"  {name[:20]:<20} | {str(stats.get('commits',0)):<8} | {str(stats.get('active_days_count',0))+' days':<12} | {files}")
             
    # Print Branch Activity Summary
    branch_act = comm.get("branch_activity", {})
    if branch_act:
        print(f"\n  🌿 Branch-wise Activity:")
        for branch, authors in branch_act.items():
            auth_str = ", ".join([f"{a}:{c}" for a,c in authors.items()])
            if len(auth_str) > 60: auth_str = auth_str[:60] + "..."
            print(f"     - {branch}: {auth_str}")

    print(f"\n[8] 📂 REPOSITORY STRUCTURE")
    print(data.get("repo_tree", "  (Tree generation failed)"))
    print("\n" + "="*80)

# ==========================================
# 7. Main Execution
# ==========================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", help="Override the default INPUT_FILE path")
    parser.add_argument("--out", default="./report", help="Output dir")
    parser.add_argument("--providers", nargs="+", default=[], help="LLM providers")
    parser.add_argument("--batch", action="store_true", help="Force batch mode")
    
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        print("❌ FATAL: OPENAI_API_KEY not found in .env file.")
        print("   Please create a .env file with: OPENAI_API_KEY=your_key")
        sys.exit(1)

    # Use CLI arg if provided, else use config
    target_input = args.input if args.input else INPUT_FILE
    
    if not target_input:
        print("❌ Error: No input provided.")
        print("   Usage:")
        print("     Single repo:  python -m src.core.agent <repo_url>")
        print("     Batch mode:   python -m src.core.agent <input_file.xlsx>")
        print("   Or set DEFAULT_INPUT_FILE environment variable")
        sys.exit(1)
    
    if not target_input.startswith("http"):
        target_input = os.path.abspath(target_input)

    try:
        is_url = target_input.startswith("http")
        is_file = os.path.exists(target_input)
        
        if is_file:
            print(f"🚀 Running BATCH MODE using file: {target_input}")
            run_batch_mode(target_input, args.out, args.providers, openai_key)
        elif is_url:
            print(f"🚀 Running SINGLE MODE on URL: {target_input}")
            res = build_pipeline(target_input, args.out, args.providers, openai_key)
            data = res.get("final_report", {})
            print_single_report(data)
            save_csv_results(args.out, "Project", data)
            print(f"\n[SUCCESS] Report & CSVs saved to {os.path.abspath(args.out)}")
        else:
            print(f"❌ Error: Input '{target_input}' is invalid.")

    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
