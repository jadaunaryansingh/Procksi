"""
Documentation Completeness Analyzer

Comprehensive documentation assessment beyond just inline comments.
Analyzes README quality, API docs, inline comments, and documentation coverage.
"""

import os
import re
from typing import Dict, Any, List, Optional


# Essential README sections (weighted by importance)
README_SECTIONS = {
    "title": {"patterns": [r'^#\s+.+'], "weight": 5, "name": "Project Title"},
    "description": {"patterns": [r'##\s*(?:About|Description|Overview|What)', r'^[A-Z].*project.*(?:is|for|helps)'], "weight": 15, "name": "Description"},
    "installation": {"patterns": [r'##\s*(?:Installation|Setup|Getting Started|Quick Start)', r'npm install', r'pip install', r'git clone'], "weight": 20, "name": "Installation Instructions"},
    "usage": {"patterns": [r'##\s*(?:Usage|How to|Examples?|Demo)', r'```'], "weight": 15, "name": "Usage Examples"},
    "features": {"patterns": [r'##\s*Features?', r'(?:^|\n)\s*[-*]\s+.+'], "weight": 10, "name": "Features List"},
    "api_docs": {"patterns": [r'##\s*(?:API|Endpoints?|Documentation)', r'/api/', r'swagger', r'openapi'], "weight": 10, "name": "API Documentation"},
    "screenshots": {"patterns": [r'!\[.*?\]\(.+\.(?:png|jpg|gif|jpeg|webp)', r'##\s*Screenshots?'], "weight": 5, "name": "Screenshots/Visuals"},
    "technologies": {"patterns": [r'##\s*(?:Tech Stack|Technologies|Built With)', r'(?:React|Vue|Angular|Django|Flask|Express|Spring)'], "weight": 5, "name": "Tech Stack"},
    "contributing": {"patterns": [r'##\s*Contributing', r'CONTRIBUTING\.md'], "weight": 3, "name": "Contributing Guidelines"},
    "license": {"patterns": [r'##\s*License', r'LICENSE', r'MIT License', r'Apache'], "weight": 5, "name": "License"},
    "contact": {"patterns": [r'##\s*(?:Contact|Authors?|Maintainers?|Contributors?)', r'(?:@|mailto:|twitter\.com|linkedin\.com)'], "weight": 2, "name": "Contact/Authors"}
}


def find_readme(repo_path: str) -> Optional[str]:
    """Find and return README content."""
    readme_patterns = ['README.md', 'README.MD', 'readme.md', 'README', 'README.txt', 'README.rst']
    
    for pattern in readme_patterns:
        readme_path = os.path.join(repo_path, pattern)
        if os.path.exists(readme_path):
            try:
                with open(readme_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            except:
                continue
    
    return None


def analyze_readme_completeness(readme_content: str) -> Dict[str, Any]:
    """Analyze README content for completeness."""
    if not readme_content:
        return {
            "has_readme": False,
            "score": 0,
            "sections_found": [],
            "sections_missing": list(README_SECTIONS.keys()),
            "word_count": 0,
            "quality_rating": "None"
        }
    
    # Normalize content for analysis
    content_lower = readme_content.lower()
    
    sections_found = []
    sections_missing = []
    total_score = 0
    max_score = sum(section["weight"] for section in README_SECTIONS.values())
    
    # Check for each section
    for section_key, section_info in README_SECTIONS.items():
        found = False
        
        for pattern in section_info["patterns"]:
            if re.search(pattern, readme_content, re.IGNORECASE | re.MULTILINE):
                found = True
                break
        
        if found:
            sections_found.append(section_info["name"])
            total_score += section_info["weight"]
        else:
            sections_missing.append(section_info["name"])
    
    # Calculate percentage score
    percentage_score = (total_score / max_score) * 100
    
    # Word count (quality indicator)
    word_count = len(readme_content.split())
    
    # Quality rating
    if percentage_score >= 80 and word_count >= 500:
        quality_rating = "Excellent"
    elif percentage_score >= 60 and word_count >= 300:
        quality_rating = "Good"
    elif percentage_score >= 40 and word_count >= 150:
        quality_rating = "Basic"
    elif percentage_score >= 20:
        quality_rating = "Minimal"
    else:
        quality_rating = "Poor"
    
    return {
        "has_readme": True,
        "score": round(percentage_score, 1),
        "sections_found": sections_found,
        "sections_missing": sections_missing,
        "word_count": word_count,
        "quality_rating": quality_rating,
        "has_code_examples": "```" in readme_content,
        "has_images": bool(re.search(r'!\[.*?\]\(.+\)', readme_content)),
        "has_links": bool(re.search(r'\[.*?\]\(https?://.+\)', readme_content))
    }


def check_api_documentation(repo_path: str) -> Dict[str, Any]:
    """Check for API documentation (Swagger, OpenAPI, etc.)."""
    api_doc_indicators = {
        "swagger": ["swagger.json", "swagger.yaml", "swagger.yml"],
        "openapi": ["openapi.json", "openapi.yaml", "openapi.yml"],
        "postman": ["postman_collection.json", ".postman/"],
        "docs_folder": ["docs/", "documentation/", "api_docs/"],
        "jsdoc": ["jsdoc.json", ".jsdoc"],
        "sphinx": ["conf.py", "docs/conf.py"],
        "mkdocs": ["mkdocs.yml"]
    }
    
    found_docs = []
    
    for doc_type, files in api_doc_indicators.items():
        for file_path in files:
            full_path = os.path.join(repo_path, file_path)
            
            # Check for directory
            if file_path.endswith('/'):
                if os.path.isdir(full_path.rstrip('/')):
                    found_docs.append(doc_type)
                    break
            # Check for file
            elif os.path.exists(full_path):
                found_docs.append(doc_type)
                break
    
    has_api_docs = len(found_docs) > 0
    
    # Score: 0-40 points for API documentation
    if has_api_docs:
        # Base 20 points for having any API docs
        score = 20
        # Additional 5 points per doc type (up to 40 total)
        score += min(20, (len(found_docs) - 1) * 5)
    else:
        score = 0
    
    return {
        "has_api_docs": has_api_docs,
        "api_doc_types": found_docs,
        "api_docs_score": score
    }


def analyze_inline_documentation(repo_path: str) -> Dict[str, Any]:
    """Analyze inline code comments and docstrings."""
    total_lines = 0
    total_comments = 0
    files_analyzed = 0
    
    code_extensions = ['.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.go', '.rs', '.cs', '.php']
    
    for root, _, files in os.walk(repo_path):
        # Skip common ignored directories
        if any(skip in root for skip in ['.git', 'node_modules', 'venv', '__pycache__', 'dist', 'build', 'target']):
            continue
        
        for f in files:
            if any(f.endswith(ext) for ext in code_extensions):
                full_path = os.path.join(root, f)
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as file:
                        content = file.read()
                        lines = content.split('\n')
                        
                        # Count non-empty lines
                        code_lines = len([l for l in lines if l.strip()])
                        
                        # Count comments (language-specific patterns)
                        comment_count = 0
                        
                        # Single-line comments (// and #)
                        comment_count += len([l for l in lines if l.strip().startswith('//') or l.strip().startswith('#')])
                        
                        # Multi-line comments (/* */ and """ """)
                        comment_count += len(re.findall(r'/\*[\s\S]*?\*/', content))
                        comment_count += len(re.findall(r'"""[\s\S]*?"""', content))
                        comment_count += len(re.findall(r"'''[\s\S]*?'''", content))
                        
                        total_lines += code_lines
                        total_comments += comment_count
                        files_analyzed += 1
                
                except:
                    continue
    
    if total_lines == 0:
        return {
            "inline_docs_score": 0,
            "comment_ratio": 0.0,
            "files_analyzed": 0
        }
    
    # Calculate comment ratio
    comment_ratio = total_comments / total_lines
    
    # Score: 0-30 points for inline documentation
    # Ideal ratio is 15-20% (1 comment per 5-7 lines)
    if comment_ratio >= 0.15:
        inline_score = 30
    elif comment_ratio >= 0.10:
        inline_score = 25
    elif comment_ratio >= 0.05:
        inline_score = 15
    else:
        inline_score = int(comment_ratio * 300)  # Scale up small ratios
    
    return {
        "inline_docs_score": min(30, inline_score),
        "comment_ratio": round(comment_ratio, 3),
        "total_comments": total_comments,
        "total_lines": total_lines,
        "files_analyzed": files_analyzed
    }


def analyze_documentation_completeness(repo_path: str) -> Dict[str, Any]:
    """
    Comprehensive documentation analysis.
    
    Scoring breakdown (0-100):
    - README completeness: 0-40 points
    - API documentation: 0-30 points  
    - Inline comments: 0-30 points
    
    Returns overall documentation score and detailed breakdown.
    """
    if not repo_path or not os.path.exists(repo_path):
        print(f"⚠️ Documentation analysis skipped: invalid repo_path ({repo_path})")
        return {
            "documentation_score": 0,
            "readme_analysis": {},
            "api_docs_analysis": {},
            "inline_docs_analysis": {},
            "overall_rating": "None"
        }
    
    print(f"      📚 Analyzing documentation completeness...")
    
    # 1. README Analysis (0-40 points)
    readme_content = find_readme(repo_path)
    readme_analysis = analyze_readme_completeness(readme_content)
    
    # Convert README score (0-100) to weighted score (0-40)
    readme_score = (readme_analysis["score"] / 100) * 40
    
    if readme_analysis["has_readme"]:
        print(f"      ✅ README found: {readme_analysis['quality_rating']} ({len(readme_analysis['sections_found'])} sections)")
    else:
        print(f"      ⚠️  No README file found")
    
    # 2. API Documentation Analysis (0-30 points)
    api_docs_analysis = check_api_documentation(repo_path)
    api_docs_score = api_docs_analysis["api_docs_score"]
    
    if api_docs_analysis["has_api_docs"]:
        print(f"      ✅ API documentation found: {', '.join(api_docs_analysis['api_doc_types'])}")
    
    # 3. Inline Documentation Analysis (0-30 points)
    inline_docs_analysis = analyze_inline_documentation(repo_path)
    inline_docs_score = inline_docs_analysis["inline_docs_score"]
    
    if inline_docs_analysis["files_analyzed"] > 0:
        print(f"      ✅ Inline comments: {inline_docs_analysis['comment_ratio']:.1%} ratio ({inline_docs_analysis['total_comments']} comments)")
    
    # Calculate overall documentation score
    total_score = readme_score + api_docs_score + inline_docs_score
    
    # Overall rating
    if total_score >= 80:
        overall_rating = "Excellent"
    elif total_score >= 60:
        overall_rating = "Good"
    elif total_score >= 40:
        overall_rating = "Adequate"
    elif total_score >= 20:
        overall_rating = "Minimal"
    else:
        overall_rating = "Poor"
    
    print(f"      ✅ Documentation score: {int(total_score)}/100 ({overall_rating})")
    
    return {
        "documentation_score": int(total_score),
        "readme_analysis": readme_analysis,
        "api_docs_analysis": api_docs_analysis,
        "inline_docs_analysis": inline_docs_analysis,
        "overall_rating": overall_rating,
        "score_breakdown": {
            "readme_score": round(readme_score, 1),
            "api_docs_score": api_docs_score,
            "inline_docs_score": inline_docs_score
        }
    }
