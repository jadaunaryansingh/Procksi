import os
from src.utils.file_utils import read_file


def _compress_section(block: str, quota: int) -> str:
    """Compress a section while preserving both header and tail evidence."""
    if len(block) <= quota:
        return block

    marker = "\n...[SECTION TRUNCATED FOR CONTEXT BUDGET]...\n"
    if quota <= len(marker) + 120:
        return block[:quota]

    body_budget = quota - len(marker)
    head_chars = int(body_budget * 0.65)
    tail_chars = body_budget - head_chars
    return f"{block[:head_chars]}{marker}{block[-tail_chars:]}"


def _enforce_budget_preserving_sections(text: str, max_chars: int) -> str:
    """Enforce character budget while retaining evidence from all major sections."""
    if len(text) <= max_chars:
        return text

    raw_blocks = text.split("\n\n=== ")
    blocks = []
    for idx, block in enumerate(raw_blocks):
        if idx == 0:
            blocks.append(block)
        else:
            blocks.append(f"=== {block}")

    if len(blocks) == 1:
        return _compress_section(blocks[0], max_chars)

    compressed_blocks = []
    remaining = max_chars
    min_quota = 900

    for index, block in enumerate(blocks):
        blocks_left = len(blocks) - index
        if remaining <= 0:
            break

        separator_cost = 2 if compressed_blocks else 0
        effective_remaining = max(0, remaining - separator_cost)
        if blocks_left <= 0:
            break

        fair_share = max(min_quota, effective_remaining // blocks_left)
        quota = min(len(block), fair_share)
        piece = _compress_section(block, quota)
        compressed_blocks.append(piece)

        assembled = "\n\n".join(compressed_blocks)
        remaining = max_chars - len(assembled)

    result = "\n\n".join(compressed_blocks)
    if len(result) > max_chars:
        result = result[:max_chars]

    if len(result) < len(text):
        note = "\n\n[SUMMARY COMPRESSED TO FIT CONTEXT BUDGET]"
        if len(result) + len(note) <= max_chars:
            result += note

    return result

def generate_repo_summary(repo_path: str, max_chars: int = 50000) -> str:
    """
    Compresses the repository into a comprehensive text summary for the LLM.
    Enhanced to provide better context for functional assessment.
    """
    # Validate repo_path
    if not repo_path or not os.path.exists(repo_path):
        return f"Repository summary unavailable: invalid path ({repo_path})"
    
    summary = []
    
    # 1. Directory Tree (with counts)
    summary.append("=== DIRECTORY STRUCTURE ===")
    file_counts = {"total": 0, "code": 0, "config": 0, "docs": 0, "assets": 0}
    
    for root, dirs, files in os.walk(repo_path):
        # Skip common non-essential directories
        dirs[:] = [d for d in dirs if d not in {
            '.git', 'node_modules', '__pycache__', '.venv', 'venv', 'dist', 
            'build', 'target', '.next', '.cache', 'coverage'
        }]
        
        level = root.replace(repo_path, '').count(os.sep)
        indent = ' ' * 2 * level
        folder_name = os.path.basename(root) or "root"
        summary.append(f"{indent}{folder_name}/")
        
        for f in files:
            if f.startswith("."):
                continue
            summary.append(f"{indent}  {f}")
            file_counts["total"] += 1
            
            # Categorize files
            if f.endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".cpp", ".go", ".rs", ".php")):
                file_counts["code"] += 1
            elif f.endswith((".json", ".yaml", ".yml", ".toml", ".ini", ".env", ".config")):
                file_counts["config"] += 1
            elif f.endswith((".md", ".txt", ".rst", ".adoc")):
                file_counts["docs"] += 1
            elif f.endswith((".png", ".jpg", ".svg", ".css", ".scss")):
                file_counts["assets"] += 1
    
    summary.append(f"\nFile Stats: {file_counts['total']} total, {file_counts['code']} code, {file_counts['config']} config, {file_counts['docs']} docs")
    
    # 2. Critical Configuration Files (Full Read)
    summary.append("\n\n=== CONFIGURATION FILES ===")
    critical_configs = [
        "README.md", "README.txt",
        "package.json", "package-lock.json",
        "requirements.txt", "Pipfile", "pyproject.toml",
        "Dockerfile", "docker-compose.yml",
        ".env.example", "config.json", "app.config.js",
        "tsconfig.json", "vite.config.ts", "webpack.config.js",
        "Cargo.toml", "go.mod", "pom.xml", "build.gradle"
    ]
    
    for fname in critical_configs:
        p = os.path.join(repo_path, fname)
        if os.path.exists(p):
            content = read_file(p)
            # Show more of config files (they're usually important)
            summary.append(f"\n--- {fname} ({len(content)} chars) ---\n{content[:3000]}")
    
    # 3. Database Schema Files
    summary.append("\n\n=== DATABASE SCHEMAS ===")
    schema_patterns = ["schema.sql", "models.py", "database.sql", "migrations", "prisma.schema"]
    schema_files = []
    
    for root, _, files in os.walk(repo_path):
        for f in files:
            if any(pattern in f.lower() for pattern in schema_patterns):
                if f.endswith((".sql", ".py", ".prisma", ".ts")):
                    schema_files.append(os.path.join(root, f))
    
    if schema_files:
        for fpath in schema_files[:5]:  # Top 5 schema files
            rel = fpath.replace(repo_path, "")
            content = read_file(fpath)
            summary.append(f"\n--- SCHEMA: {rel} ---\n{content[:2000]}")
    else:
        summary.append("No database schema files detected")
    
    # 4. API/Backend Files (Routes, Controllers, Services)
    summary.append("\n\n=== BACKEND/API IMPLEMENTATION ===")
    backend_files = []
    backend_keywords = ["route", "controller", "api", "endpoint", "server", "main", "app", "handler", "service"]
    
    for root, _, files in os.walk(repo_path):
        for f in files:
            if f.endswith((".py", ".js", ".ts", ".go", ".java", ".php", ".rs")):
                f_lower = f.lower()
                if any(keyword in f_lower for keyword in backend_keywords):
                    fpath = os.path.join(root, f)
                    backend_files.append((fpath, os.path.getsize(fpath)))
    
    # Sort by size and relevance
    backend_files.sort(key=lambda x: x[1], reverse=True)
    
    if backend_files:
        for fpath, _ in backend_files[:8]:  # Top 8 backend files
            rel = fpath.replace(repo_path, "")
            content = read_file(fpath)
            summary.append(f"\n--- BACKEND: {rel} ({os.path.getsize(fpath)} bytes) ---\n{content[:4000]}")
    else:
        summary.append("No backend/API files detected")
    
    # 5. Frontend Files (Components, Pages, Views)
    summary.append("\n\n=== FRONTEND IMPLEMENTATION ===")
    frontend_files = []
    frontend_patterns = [
        ("component", 3000), ("page", 3000), ("view", 2500), 
        ("App.jsx", 4000), ("App.tsx", 4000), ("index", 2000),
        ("main.jsx", 3000), ("main.tsx", 3000)
    ]
    
    for root, _, files in os.walk(repo_path):
        for f in files:
            if f.endswith((".jsx", ".tsx", ".vue", ".svelte", ".html")):
                fpath = os.path.join(root, f)
                # Determine priority
                priority = 1
                for pattern, _ in frontend_patterns:
                    if pattern.lower() in f.lower():
                        priority = 0
                        break
                frontend_files.append((fpath, priority, os.path.getsize(fpath)))
    
    # Sort by priority, then size
    frontend_files.sort(key=lambda x: (x[1], -x[2]))
    
    if frontend_files:
        for fpath, _, size in frontend_files[:6]:  # Top 6 frontend files
            rel = fpath.replace(repo_path, "")
            content = read_file(fpath)
            summary.append(f"\n--- FRONTEND: {rel} ({size} bytes) ---\n{content[:3000]}")
    else:
        summary.append("No frontend component files detected")
    
    # 6. Core Business Logic Files (remaining important code)
    summary.append("\n\n=== CORE BUSINESS LOGIC ===")
    core_files = []
    
    for root, _, files in os.walk(repo_path):
        for f in files:
            if f.endswith((".py", ".js", ".ts", ".java", ".cpp", ".go")):
                fpath = os.path.join(root, f)
                # Skip if already included
                if fpath in [bf[0] for bf in backend_files] or fpath in [ff[0] for ff in frontend_files]:
                    continue
                # Skip test files
                if "test" in f.lower() or "spec" in f.lower():
                    continue
                core_files.append((fpath, os.path.getsize(fpath)))
    
    # Sort by size (largest likely have main logic)
    core_files.sort(key=lambda x: x[1], reverse=True)
    
    current_chars = len("\n".join(summary))
    for fpath, size in core_files[:8]:  # Top 8 additional files
        if current_chars > max_chars:
            summary.append(f"\n[TRUNCATED - Character limit reached at {max_chars}]")
            break
        rel = fpath.replace(repo_path, "")
        content = read_file(fpath)
        snippet = content[:2500]
        summary.append(f"\n--- CORE: {rel} ({size} bytes) ---\n{snippet}")
        current_chars += len(snippet)
    
    final_summary = "\n".join(summary)
    return _enforce_budget_preserving_sections(final_summary, max_chars)