import os
from typing import List

def detect_tech_stack(repo_path: str) -> List[str]:
    # Validate repo_path
    if not repo_path or not os.path.exists(repo_path):
        print(f"⚠️ Tech stack detection skipped: invalid repo_path ({repo_path})")
        return ["Unknown"]
    
    stack = set()
    files = set()
    
    # Collect all filenames for heuristic
    for root, _, filenames in os.walk(repo_path):
        for f in filenames:
            files.add(f.lower())

    # Backend / Languages
    if "requirements.txt" in files or "pyproject.toml" in files: stack.add("Python")
    if "package.json" in files: stack.add("Node.js")
    if "pom.xml" in files: stack.add("Java")
    if "go.mod" in files: stack.add("Go")
    if "composer.json" in files: stack.add("PHP")
    
    # Frameworks & Tools
    if "dockerfile" in files: stack.add("Docker")
    if "manage.py" in files: stack.add("Django")
    if "flask" in str(files): stack.add("Flask") # Loose heuristic
    if "next.config.js" in files: stack.add("Next.js")
    if "tailwind.config.js" in files: stack.add("Tailwind")
    
    # Fallback
    if not stack:
        if any(f.endswith(".py") for f in files): stack.add("Python")
        elif any(f.endswith(".js") for f in files): stack.add("JavaScript")
        else: stack.add("Generic/Unknown")
            
    return sorted(list(stack))