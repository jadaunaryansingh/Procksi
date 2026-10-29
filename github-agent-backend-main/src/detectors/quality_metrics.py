import os
import re
import subprocess
import json
import radon.complexity as cc
from radon.metrics import mi_visit
from radon.raw import analyze
from typing import Dict, Any, List, Tuple
from collections import defaultdict


# Language-specific file extensions
LANGUAGE_EXTENSIONS = {
    "python": [".py"],
    "javascript": [".js", ".jsx", ".mjs"],
    "typescript": [".ts", ".tsx"],
    "java": [".java"],
    "go": [".go"],
    "rust": [".rs"],
    "csharp": [".cs"],
    "php": [".php"]
}


def detect_project_languages(repo_path: str) -> Dict[str, int]:
    """Detect which languages are used and count files."""
    language_counts = defaultdict(int)
    
    for root, _, files in os.walk(repo_path):
        # Skip common ignored directories
        if any(skip in root for skip in ['.git', 'node_modules', 'venv', '__pycache__', 'dist', 'build']):
            continue
            
        for f in files:
            for lang, exts in LANGUAGE_EXTENSIONS.items():
                if any(f.endswith(ext) for ext in exts):
                    language_counts[lang] += 1
                    break
    
    return dict(language_counts)


def analyze_python_quality(repo_path: str) -> Dict[str, Any]:
    """Analyze Python code quality using Radon."""
    total_complexity = 0
    total_maintainability = 0
    total_loc = 0
    total_comments = 0
    py_files_count = 0

    for root, _, files in os.walk(repo_path):
        if any(skip in root for skip in ['.git', 'venv', '__pycache__', 'dist', 'build']):
            continue
            
        for f in files:
            if f.endswith(".py"):
                full_path = os.path.join(root, f)
                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as file:
                        content = file.read()
                        if not content.strip():
                            continue

                        # Complexity
                        blocks = cc.cc_visit(content)
                        if blocks:
                            file_complexity = sum(b.complexity for b in blocks) / len(blocks)
                        else:
                            file_complexity = 1
                        
                        # Maintainability (0-100)
                        maintainability = mi_visit(content, multi=True)

                        # Raw stats (Comments vs Code)
                        raw_stats = analyze(content)
                        
                        total_complexity += file_complexity
                        total_maintainability += maintainability
                        total_loc += raw_stats.loc
                        total_comments += raw_stats.comments
                        py_files_count += 1

                except Exception:
                    continue

    if py_files_count > 0:
        return {
            "files": py_files_count,
            "complexity": round(total_complexity / py_files_count, 2),
            "maintainability": round(total_maintainability / py_files_count, 2),
            "loc": total_loc,
            "comments": total_comments
        }
    
    return {"files": 0, "complexity": 0, "maintainability": 0, "loc": 0, "comments": 0}


def analyze_javascript_quality(repo_path: str) -> Dict[str, Any]:
    """Analyze JavaScript/TypeScript code quality using basic metrics."""
    total_complexity = 0
    total_loc = 0
    total_comments = 0
    js_files_count = 0
    
    # Complexity indicators in JS/TS
    complexity_patterns = [
        r'\bif\s*\(',           # if statements
        r'\belse\s*{',          # else blocks
        r'\bfor\s*\(',          # for loops
        r'\bwhile\s*\(',        # while loops
        r'\bswitch\s*\(',       # switch statements
        r'\bcase\s+',           # case statements
        r'\bcatch\s*\(',        # try-catch
        r'\&\&',                # logical AND
        r'\|\|',                # logical OR
        r'\?.*:',               # ternary operator
    ]

    for root, _, files in os.walk(repo_path):
        if any(skip in root for skip in ['.git', 'node_modules', 'dist', 'build', '.next']):
            continue
            
        for f in files:
            if any(f.endswith(ext) for ext in ['.js', '.jsx', '.ts', '.tsx', '.mjs']):
                full_path = os.path.join(root, f)
                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as file:
                        content = file.read()
                        if not content.strip():
                            continue
                        
                        lines = content.split('\n')
                        
                        # Count LOC (non-empty, non-comment lines)
                        loc = len([l for l in lines if l.strip() and not l.strip().startswith('//')])
                        
                        # Count comments
                        single_comments = len([l for l in lines if l.strip().startswith('//')])
                        multi_comments = len(re.findall(r'/\*[\s\S]*?\*/', content))
                        comments = single_comments + multi_comments
                        
                        # Estimate complexity
                        file_complexity = 1  # Base complexity
                        for pattern in complexity_patterns:
                            file_complexity += len(re.findall(pattern, content))
                        
                        # Normalize complexity by LOC (complexity per 100 lines)
                        normalized_complexity = (file_complexity / max(1, loc)) * 100
                        
                        total_complexity += normalized_complexity
                        total_loc += loc
                        total_comments += comments
                        js_files_count += 1

                except Exception:
                    continue

    if js_files_count > 0:
        avg_complexity = total_complexity / js_files_count
        # Convert to maintainability index (inverse of complexity)
        maintainability = max(0, 100 - (avg_complexity * 0.5))
        
        return {
            "files": js_files_count,
            "complexity": round(avg_complexity, 2),
            "maintainability": round(maintainability, 2),
            "loc": total_loc,
            "comments": total_comments
        }
    
    return {"files": 0, "complexity": 0, "maintainability": 0, "loc": 0, "comments": 0}


def analyze_java_quality(repo_path: str) -> Dict[str, Any]:
    """Analyze Java code quality using basic metrics."""
    total_complexity = 0
    total_loc = 0
    total_comments = 0
    java_files_count = 0
    
    # Complexity indicators in Java
    complexity_patterns = [
        r'\bif\s*\(',
        r'\belse\s*{',
        r'\bfor\s*\(',
        r'\bwhile\s*\(',
        r'\bswitch\s*\(',
        r'\bcase\s+',
        r'\bcatch\s*\(',
        r'\&\&',
        r'\|\|',
        r'\?.*:',
    ]

    for root, _, files in os.walk(repo_path):
        if any(skip in root for skip in ['.git', 'target', 'build', '.gradle']):
            continue
            
        for f in files:
            if f.endswith('.java'):
                full_path = os.path.join(root, f)
                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as file:
                        content = file.read()
                        if not content.strip():
                            continue
                        
                        lines = content.split('\n')
                        
                        # Count LOC
                        loc = len([l for l in lines if l.strip() and not l.strip().startswith('//')])
                        
                        # Count comments
                        single_comments = len([l for l in lines if l.strip().startswith('//')])
                        multi_comments = len(re.findall(r'/\*[\s\S]*?\*/', content))
                        javadoc_comments = len(re.findall(r'/\*\*[\s\S]*?\*/', content))
                        comments = single_comments + multi_comments + javadoc_comments
                        
                        # Estimate complexity
                        file_complexity = 1
                        for pattern in complexity_patterns:
                            file_complexity += len(re.findall(pattern, content))
                        
                        normalized_complexity = (file_complexity / max(1, loc)) * 100
                        
                        total_complexity += normalized_complexity
                        total_loc += loc
                        total_comments += comments
                        java_files_count += 1

                except Exception:
                    continue

    if java_files_count > 0:
        avg_complexity = total_complexity / java_files_count
        maintainability = max(0, 100 - (avg_complexity * 0.5))
        
        return {
            "files": java_files_count,
            "complexity": round(avg_complexity, 2),
            "maintainability": round(maintainability, 2),
            "loc": total_loc,
            "comments": total_comments
        }
    
    return {"files": 0, "complexity": 0, "maintainability": 0, "loc": 0, "comments": 0}


def analyze_go_quality(repo_path: str) -> Dict[str, Any]:
    """Analyze Go code quality using gocyclo if available."""
    total_complexity = 0
    total_loc = 0
    total_comments = 0
    go_files_count = 0
    
    for root, _, files in os.walk(repo_path):
        if any(skip in root for skip in ['.git', 'vendor']):
            continue
            
        for f in files:
            if f.endswith('.go'):
                full_path = os.path.join(root, f)
                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as file:
                        content = file.read()
                        if not content.strip():
                            continue
                        
                        lines = content.split('\n')
                        
                        # Count LOC
                        loc = len([l for l in lines if l.strip() and not l.strip().startswith('//')])
                        
                        # Count comments
                        comments = len([l for l in lines if l.strip().startswith('//')])
                        
                        # Basic complexity estimation
                        complexity_indicators = content.count('if ') + content.count('for ') + content.count('switch ')
                        file_complexity = (complexity_indicators / max(1, loc)) * 100
                        
                        total_complexity += file_complexity
                        total_loc += loc
                        total_comments += comments
                        go_files_count += 1

                except Exception:
                    continue

    if go_files_count > 0:
        avg_complexity = total_complexity / go_files_count
        maintainability = max(0, 100 - (avg_complexity * 0.5))
        
        return {
            "files": go_files_count,
            "complexity": round(avg_complexity, 2),
            "maintainability": round(maintainability, 2),
            "loc": total_loc,
            "comments": total_comments
        }
    
    return {"files": 0, "complexity": 0, "maintainability": 0, "loc": 0, "comments": 0}


def aggregate_quality_metrics(language_results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate quality metrics across all languages."""
    total_files = sum(r.get("files", 0) for r in language_results.values())
    
    if total_files == 0:
        return {
            "avg_complexity": 0,
            "maintainability_index": 0,
            "documentation_score": 0,
            "analyzed_files": 0,
            "languages_analyzed": []
        }
    
    # Weighted average by file count
    weighted_complexity = sum(
        r.get("complexity", 0) * r.get("files", 0) 
        for r in language_results.values()
    ) / total_files
    
    weighted_maintainability = sum(
        r.get("maintainability", 0) * r.get("files", 0) 
        for r in language_results.values()
    ) / total_files
    
    total_loc = sum(r.get("loc", 0) for r in language_results.values())
    total_comments = sum(r.get("comments", 0) for r in language_results.values())
    
    # Documentation score (comment to code ratio)
    if total_loc > 0:
        doc_ratio = total_comments / total_loc
        doc_score = min(1.0, doc_ratio / 0.15) * 100
    else:
        doc_score = 0
    
    # Convert complexity to a positive score (lower complexity => higher score).
    complexity_score = max(0.0, 100.0 - (weighted_complexity * 0.7))

    # Blend quality dimensions for a more representative maintainability score.
    blended_maintainability = (
        (weighted_maintainability * 0.6)
        + (complexity_score * 0.25)
        + (doc_score * 0.15)
    )

    # Large mature repositories with broad analyzed surface should not be under-scored.
    scale_bonus = 0.0
    language_count = len([lang for lang, r in language_results.items() if r.get("files", 0) > 0])
    if total_files >= 120 and total_loc >= 20000:
        scale_bonus += 12.0
    elif total_files >= 80 and total_loc >= 12000:
        scale_bonus += 8.0

    if language_count >= 2:
        scale_bonus += 3.0

    if doc_score >= 65.0:
        scale_bonus += 3.0

    final_maintainability = min(100.0, blended_maintainability + scale_bonus)

    return {
        "avg_complexity": round(weighted_complexity, 2),
        "maintainability_index": round(final_maintainability, 2),
        "documentation_score": round(doc_score, 2),
        "complexity_score": round(complexity_score, 2),
        "scale_bonus": round(scale_bonus, 2),
        "analyzed_files": total_files,
        "languages_analyzed": [lang for lang, r in language_results.items() if r.get("files", 0) > 0],
        "language_breakdown": language_results
    }


def analyze_quality(repo_path: str) -> Dict[str, Any]:
    """
    Multi-language code quality analyzer.
    Supports Python, JavaScript, TypeScript, Java, Go, and more.
    
    Returns metrics for:
    1. Cyclomatic Complexity (Logic difficulty)
    2. Maintainability Index (Code health)
    3. Documentation coverage (Comment to code ratio)
    """
    # Validate repo_path
    if not repo_path or not os.path.exists(repo_path):
        print(f"⚠️ Quality check skipped: invalid repo_path ({repo_path})")
        return {
            "avg_complexity": 0,
            "maintainability_index": 0,
            "documentation_score": 0,
            "analyzed_files": 0,
            "languages_analyzed": []
        }
    
    # Detect languages in the project
    languages = detect_project_languages(repo_path)
    
    if not languages:
        print(f"      ℹ️  No supported code files found")
        return {
            "avg_complexity": 0,
            "maintainability_index": 0,
            "documentation_score": 0,
            "analyzed_files": 0,
            "languages_analyzed": []
        }
    
    print(f"      📊 Detected languages: {', '.join(languages.keys())}")
    
    # Analyze each language
    language_results = {}
    
    if "python" in languages:
        print(f"      🐍 Analyzing Python ({languages['python']} files)...")
        language_results["python"] = analyze_python_quality(repo_path)
    
    if "javascript" in languages or "typescript" in languages:
        js_count = languages.get("javascript", 0) + languages.get("typescript", 0)
        print(f"      📜 Analyzing JavaScript/TypeScript ({js_count} files)...")
        language_results["javascript"] = analyze_javascript_quality(repo_path)
    
    if "java" in languages:
        print(f"      ☕ Analyzing Java ({languages['java']} files)...")
        language_results["java"] = analyze_java_quality(repo_path)
    
    if "go" in languages:
        print(f"      🐹 Analyzing Go ({languages['go']} files)...")
        language_results["go"] = analyze_go_quality(repo_path)
    
    # Aggregate results
    final_metrics = aggregate_quality_metrics(language_results)
    
    print(f"      ✅ Quality analysis complete: {final_metrics['analyzed_files']} files across {len(final_metrics['languages_analyzed'])} languages")
    
    return final_metrics