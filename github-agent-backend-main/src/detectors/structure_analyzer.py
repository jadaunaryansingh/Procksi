import os
from typing import Dict, Any, List

# Common folder patterns for architectures
ARCH_PATTERNS = {
    "MVC (Model-View-Controller)": {"required": ["models", "views", "controllers"], "threshold": 2},
    "Clean Architecture": {"required": ["domain", "use_cases", "data", "presentation", "core"], "threshold": 2},
    "Microservices": {"required": ["services", "api-gateway", "kubernetes", "docker", "proto"], "threshold": 2},
    "Modern React/Next": {"required": ["components", "hooks", "context", "pages", "public", "app"], "threshold": 3},
    "Django Standard": {"required": ["migrations", "templates", "static", "apps"], "threshold": 3},
    "Standard Go": {"required": ["cmd", "internal", "pkg", "api"], "threshold": 2},
    "Flutter/Mobile": {"required": ["lib", "ios", "android", "assets"], "threshold": 3}
}

def analyze_structure(repo_path: str) -> Dict[str, Any]:
    # Validate repo_path
    if not repo_path or not os.path.exists(repo_path):
        print(f"⚠️ Structure analysis skipped: invalid repo_path ({repo_path})")
        return {
            "architecture": "Unknown",
            "organization_score": 50,
            "has_tests": False,
            "has_docs": False
        }
    """
    Analyzes directory structure for architecture patterns and nesting depth.
    """
    folders = set()
    max_depth = 0
    total_folders = 0
    root_file_count = 0
    
    # 1. Walk the tree to gather stats
    base_depth = repo_path.rstrip(os.path.sep).count(os.path.sep)
    
    for root, dirs, files in os.walk(repo_path):
        # Ignore hidden/git folders
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        # Track depth
        current_depth = root.count(os.path.sep) - base_depth
        if current_depth > max_depth:
            max_depth = current_depth
            
        # Collect folder names for pattern matching
        for d in dirs:
            folders.add(d.lower())
            total_folders += 1
            
        # Check root level clutter (files in the base folder)
        if current_depth == 0:
            root_file_count = len([f for f in files if not f.startswith('.')])

    # 2. Detect Architecture Pattern
    detected_arch = "Monolithic / Unstructured"
    
    for arch_name, rules in ARCH_PATTERNS.items():
        matches = 0
        for req in rules["required"]:
            # Check if required folder exists (partial match allowed, e.g. 'user_models')
            if req in folders or any(req in f for f in folders):
                matches += 1
        
        if matches >= rules["threshold"]:
            detected_arch = arch_name
            break # Stop at first match

    # 3. Calculate Organization Score (0-100)
    # Start at 100, deduct for bad practices
    org_score = 100
    
    # Penalty: "Spaghetti in Root" (Too many files in root, very few folders)
    if root_file_count > 15 and total_folders < 3:
        org_score -= 40
        if detected_arch == "Monolithic / Unstructured":
            detected_arch = "Flat Spaghetti Code"
        
    # Penalty: "Nesting Hell" (Too deep)
    if max_depth > 6:
        org_score -= 20
        
    # Penalty: Empty project
    if total_folders == 0 and root_file_count < 5:
        org_score = 0
        detected_arch = "Empty / Minimal"

    return {
        "architecture": detected_arch,
        "max_depth": max_depth,
        "organization_score": max(0, org_score),
        "folder_count": total_folders,
        "root_clutter": root_file_count
    }