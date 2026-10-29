# import os
# import shutil
# import tempfile
# from git import Repo
# from typing import Tuple, List, Dict
# import subprocess

# def clone_repo(url: str, ref: str = "HEAD", depth: int = 1) -> str:
#     """
#     Shallow clone repository to a temp folder. Return path.
#     """
#     tempdir = tempfile.mkdtemp(prefix="repo_audit_")
#     try:
#         Repo.clone_from(url, tempdir, depth=depth)
#     except Exception:
#         # fallback to git CLI for some cases
#         cmd = ["git", "clone", "--depth", str(depth), url, tempdir]
#         subprocess.check_call(cmd)
#     return tempdir

# def cleanup_repo(path: str):
#     shutil.rmtree(path, ignore_errors=True)

# def list_files(repo_path: str, ext_whitelist=None):
#     ext_whitelist = ext_whitelist or [".py", ".js", ".java", ".c", ".cpp"]
#     files = []
#     for root, _, filenames in os.walk(repo_path):
#         for f in filenames:
#             if any(f.endswith(e) for e in ext_whitelist):
#                 files.append(os.path.join(root, f))
#     return files

# def get_commit_history(repo_path: str, max_commits: int = 500) -> List[Dict]:
#     r = Repo(repo_path)
#     commits = []
#     for i, commit in enumerate(r.iter_commits()):
#         if i >= max_commits:
#             break
#         commits.append({
#             "hexsha": commit.hexsha,
#             "author": commit.author.name,
#             "email": commit.author.email,
#             "message": commit.message,
#             "datetime": commit.committed_datetime.isoformat(),
#             "files": list(commit.stats.files.keys()),
#             "added": commit.stats.total.get("insertions", 0),
#             "deleted": commit.stats.total.get("deletions", 0),
#         })
#     return commits
















import os
import shutil
import tempfile
from git import Repo
from typing import Tuple, List, Dict
import subprocess

# FIX 1: Change depth to None so it downloads the full history
def clone_repo(url: str, ref: str = "HEAD", depth: int = None) -> str:
    """
    Shallow clone repository to a temp folder. Return path.
    Sanitizes GitHub URLs that include /tree/ or /blob/ references.
    """
    # Sanitize GitHub URLs that include branch/tree references
    # Example: https://github.com/user/repo/tree/main -> https://github.com/user/repo
    import re
    url = url.strip()
    
    # Remove /tree/*, /blob/*, or /commit/* from GitHub URLs
    if "github.com" in url:
        url = re.sub(r'/(tree|blob|commit)/[^/\s]+.*$', '', url)
        # Also remove trailing slashes
        url = url.rstrip('/')
    
    # Always do a fresh clone to ensure latest code is analyzed
    # Extract repo name from URL for the clone directory
    repo_name = url.rstrip('/').split('/')[-1].replace('.git', '')
    clone_dir = os.path.join("repo_cache", repo_name)
    
    # Clean up any previous clone to ensure fresh data
    if os.path.exists(clone_dir):
        print(f"      🧹 Cleaning up previous clone: {clone_dir}")
        shutil.rmtree(clone_dir, ignore_errors=True)
    
    # Create directory for fresh clone
    os.makedirs(clone_dir, exist_ok=True)
    tempdir = clone_dir
    
    try:
        # Pass depth only if it is explicitly set (not None)
        if depth:
            Repo.clone_from(url, tempdir, depth=depth)
        else:
            Repo.clone_from(url, tempdir)
    except Exception:
        # fallback to git CLI
        try:
            cmd = ["git", "clone", url, tempdir]
            if depth:
                cmd.extend(["--depth", str(depth)])
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError:
             # Retry with Auth Token if available (for private repos)
             token = os.getenv("GH_API_KEY")
             if token and "github.com" in url and "@" not in url:
                 print(f"      🔐 Retrying with GitHub Token...")
                 auth_url = url.replace("https://", f"https://{token}@")
                 cmd = ["git", "clone", auth_url, tempdir]
                 if depth:
                     cmd.extend(["--depth", str(depth)])
                 subprocess.check_call(cmd)
             else:
                 raise
    return tempdir

def cleanup_repo(path: str):
    shutil.rmtree(path, ignore_errors=True)

def list_files(repo_path: str, ext_whitelist=None):
    ext_whitelist = ext_whitelist or [".py", ".js", ".java", ".c", ".cpp"]
    
    # Exclude common vendor/build/config directories and files
    exclude_dirs = {
        "node_modules", "venv", ".venv", "env", "dist", "build", "target", 
        "bin", "obj", "vendor", "libs", "lib", "migrations", ".git", ".github",
        "__pycache__", "coverage", "test", "tests", "docs"
    }
    
    exclude_files = {
        "package-lock.json", "yarn.lock", "bun.lockb", "cargo.lock", 
        "poetry.lock", "go.sum", "pnpm-lock.yaml"
    }

    files_list = []
    
    for root, dirs, filenames in os.walk(repo_path):
        # Filter directories in-place to prevent walking them
        dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith(".")]
        
        for f in filenames:
            # 1. Check extension
            if not any(f.endswith(e) for e in ext_whitelist):
                continue
            
            # 2. Check exact exclude list
            if f in exclude_files:
                continue

            # 3. Check for minified files (usually libraries)
            if ".min." in f:
                continue
                
            # 4. Check for test files (optional, but often AI analysis focuses on logic)
            if f.endswith(".test.js") or f.endswith(".spec.js") or f.startswith("test_"):
                # Decide if you want to keep tests. Often they are AI generated too.
                # For now, let's include them as AI writes tests often.
                pass

            files_list.append(os.path.join(root, f))
            
    return files_list

def get_commit_history(repo_path: str, max_commits: int = 500) -> List[Dict]:
    r = Repo(repo_path)
    commits = []
    for i, commit in enumerate(r.iter_commits()):
        if i >= max_commits:
            break
        
        # FIX 2: Add try/except to prevent crashing on the very first/last commit
        try:
            stats = commit.stats
            files = list(stats.files.keys())
            added = stats.total.get("insertions", 0)
            deleted = stats.total.get("deletions", 0)
        except Exception:
            # If parent is missing or it's the first commit, default to 0
            files = []
            added = 0
            deleted = 0

        commits.append({
            "hexsha": commit.hexsha,
            "author": commit.author.name,
            "email": commit.author.email,
            "message": commit.message,
            "datetime": commit.committed_datetime.isoformat(),
            "files": files,
            "added": added,
            "deleted": deleted,
        })
    return commits