import re
import os
import time
from typing import Dict, Any, List
from dataclasses import dataclass, asdict

# Import new validation modules
from .entropy_calculator import (
    calculate_entropy,
    meets_entropy_threshold,
    validate_aws_secret_uniqueness,
    validate_aws_access_key_uniqueness
)
from .placeholder_detector import is_placeholder
from .context_analyzer import analyze_context
from .best_practices_detector import detect_best_practices, BestPracticeResult
from .recommendation_generator import generate_recommendations, Recommendation
from .score_calculator import calculate_security_score, SecurityScore


@dataclass
class SecurityReport:
    """Enhanced security report with all findings."""
    score: int
    secrets_score: int
    practices_score: int
    leak_count: int
    leaks: List[Dict]
    best_practices: List[Dict]
    recommendations: List[Dict]
    scan_duration: float
    files_scanned: int
    skipped_files: int = 0

# Patterns for common high-risk secrets
PATTERNS = {
    "AWS Access Key": r"(?<![A-Z0-9])[A-Z0-9]{20}(?![A-Z0-9])",
    "AWS Secret": r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+]{40}(?![A-Za-z0-9/+=])",  # Removed = from middle, AWS secrets don't have repeating =
    "Google API Key": r"AIza[0-9A-Za-z\\-_]{35}",
    "Generic Private Key": r"-----BEGIN (PRIVATE|RSA PRIVATE) KEY-----",
    "OpenAI API Key": r"sk-[a-zA-Z0-9]{48}",
    "GitHub Token": r"gh[pousr]_[A-Za-z0-9]{36}",
    "Stripe Key": r"sk_live_[0-9a-zA-Z]{24}",
    "Hardcoded Password": r"(password|passwd|pwd|secret)\s*[:=]\s*['\"][^'\"]{3,}['\"]" ,
    "DB Connection String": r"(mysql|postgresql|mongodb)://[^\s]*",
    "JWT Token": r"eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*"
}

# Files to skip (only skip obvious example/template files and binaries)
SKIP_FILES = (
    ".env.example", ".env.sample", ".env.template", "example.env", "config.example",
    ".png", ".jpg", ".gif", ".ico", ".lock", ".pyc", ".pdf"
)

# Only skip build artifacts and dependencies, not test/docs folders
SKIP_FOLDERS = ("node_modules", ".git", "dist", "build", "__pycache__", ".venv", "venv")

def scan_for_secrets(repo_path: str) -> Dict[str, Any]:
    """
    Enhanced security scan with secret detection, best practices checking,
    and actionable recommendations.
    
    Args:
        repo_path: Absolute path to repository root
        
    Returns:
        Dictionary with security report (backward compatible)
    """
    start_time = time.time()
    
    # Validate repo_path
    if not repo_path or not os.path.exists(repo_path):
        print(f"⚠️ Security scan skipped: invalid repo_path ({repo_path})")
        return {
            "score": 100,
            "leak_count": 0,
            "leaks": [],
            "details": []  # Backward compatibility
        }
    
    leaks = []
    files_scanned = 0
    skipped_files = 0
    
    # Walk through files
    for root, _, files in os.walk(repo_path):
        # Skip test/docs/example folders
        if any(skip_folder in root.lower() for skip_folder in SKIP_FOLDERS):
            continue
            
        for f in files:
            f_lower = f.lower()
            # Skip hidden files, images, docs, and example config files
            if f.startswith(".") or f_lower.endswith(SKIP_FILES):
                skipped_files += 1
                continue
            
            # Skip large files (> 1MB)
            path = os.path.join(root, f)
            try:
                if os.path.getsize(path) > 1024 * 1024:  # 1MB
                    skipped_files += 1
                    continue
            except Exception:
                skipped_files += 1
                continue
            
            files_scanned += 1
            
            try:
                # Check if binary file
                with open(path, "rb") as file_check:
                    chunk = file_check.read(1024)
                    if b'\x00' in chunk:  # Binary file indicator
                        skipped_files += 1
                        files_scanned -= 1
                        continue
                
                with open(path, "r", encoding="utf-8", errors="ignore") as file_in:
                    lines = file_in.readlines()
                    
                for i, line in enumerate(lines):
                    # Skip commented lines (enhanced detection)
                    stripped = line.strip()
                    if stripped.startswith(("#", "//", "/*", "*", "'", '"')):
                        continue
                    
                    # Skip lines that are obviously decorative (repeated characters)
                    if is_decorative_line(stripped):
                        continue
                    
                    # Skip import/require lines (common false positives for AWS Secret regex)
                    if re.match(r'^\s*(import\s|from\s|require\s*\(|export\s)', stripped):
                        continue
                    
                    # Get surrounding lines for context analysis
                    start_idx = max(0, i - 5)
                    end_idx = min(len(lines), i + 6)
                    surrounding_lines = lines[start_idx:end_idx]
                        
                    for name, pattern in PATTERNS.items():
                        matches = re.finditer(pattern, line)
                        for match in matches:
                            matched_text = match.group(0)
                            
                            # Additional validation to reduce false positives
                            if is_likely_false_positive(matched_text, name):
                                continue
                            
                            # Analyze context
                            context = analyze_context(line, surrounding_lines, path)
                            
                            # Skip if in example file
                            if context.is_example_file:
                                continue
                            
                            # Skip if confidence is too low (< 0.3)
                            if context.confidence_adjustment < 0.3:
                                continue
                            
                            # Determine severity based on context
                            if context.is_test_file or context.is_placeholder_variable:
                                severity = "low"
                            else:
                                severity = "high" if name in ["AWS Secret", "AWS Access Key", "Generic Private Key"] else "medium"
                            
                            # Record minute detail: File, Line #, Type
                            leaks.append({
                                "file": f,
                                "path": path.replace(repo_path, "").lstrip(os.sep), # Relative path
                                "line_number": i + 1,
                                "type": name,
                                "snippet": line.strip()[:100] + ("..." if len(line.strip()) > 100 else ""), # Truncated for display
                                "confidence": context.confidence_adjustment,
                                "severity": severity
                            })
            except Exception:
                continue
    
    # Detect best practices
    best_practices_results = detect_best_practices(repo_path)
    
    # Generate recommendations
    recommendations = generate_recommendations(leaks, best_practices_results)
    
    # Calculate scores
    security_score = calculate_security_score(leaks, best_practices_results)
    
    # Calculate scan duration
    scan_duration = time.time() - start_time
    
    # Convert best practices to dict for JSON serialization
    best_practices_dict = [
        {
            "practice_name": bp.practice_name,
            "status": bp.status,
            "severity": bp.severity,
            "files_found": bp.files_found,
            "recommendation": bp.recommendation,
            "code_example": bp.code_example
        }
        for bp in best_practices_results
    ]
    
    # Convert recommendations to dict
    recommendations_dict = [
        {
            "title": rec.title,
            "description": rec.description,
            "severity": rec.severity,
            "category": rec.category,
            "action_items": rec.action_items,
            "code_example": rec.code_example,
            "documentation_link": rec.documentation_link,
            "priority": rec.priority
        }
        for rec in recommendations
    ]
    
    # Return enhanced report (backward compatible)
    return {
        "score": security_score.overall_score,
        "secrets_score": security_score.secrets_score,
        "practices_score": security_score.practices_score,
        "leak_count": len(leaks),
        "leaks": leaks,
        "details": leaks,  # Backward compatibility
        "best_practices": best_practices_dict,
        "recommendations": recommendations_dict,
        "scan_duration": scan_duration,
        "files_scanned": files_scanned,
        "skipped_files": skipped_files,
        "penalty_breakdown": security_score.penalty_breakdown
    }


def is_decorative_line(line: str) -> bool:
    """Check if a line is decorative (repeated characters like ===, ---, etc.)"""
    if len(line) < 10:
        return False
    
    # Check if line is mostly repeated characters
    unique_chars = set(line.replace(" ", "").replace("\t", ""))
    if len(unique_chars) <= 3:  # Only 1-3 unique characters (like =, -, #)
        # Check if any character repeats more than 10 times
        for char in unique_chars:
            if line.count(char) >= 10:
                return True
    return False


def is_likely_false_positive(matched_text: str, secret_type: str) -> bool:
    """
    Enhanced validation to filter out false positives using entropy analysis,
    placeholder detection, and unique character validation.
    """
    
    # Check for placeholder patterns
    if is_placeholder(matched_text):
        return True
    
    # Check entropy threshold
    if not meets_entropy_threshold(matched_text, secret_type):
        return True
    
    # AWS Secret specific validation
    if secret_type == "AWS Secret":
        # Check unique character count
        if not validate_aws_secret_uniqueness(matched_text):
            return True
        
        # Check for repeated patterns (like "====")
        if any(char * 4 in matched_text for char in set(matched_text)):
            return True
    
    # AWS Access Key specific validation
    if secret_type == "AWS Access Key":
        # Check unique character count
        if not validate_aws_access_key_uniqueness(matched_text):
            return True
    
    return False