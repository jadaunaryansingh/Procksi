import os
import chardet
from typing import Tuple

def read_file(path: str) -> str:
    with open(path, "rb") as f:
        raw = f.read()
        encoding = chardet.detect(raw)["encoding"] or "utf-8"
        try:
            return raw.decode(encoding, errors="ignore")
        except Exception:
            return raw.decode("utf-8", errors="ignore")

def detect_language(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    mapping = {
        ".py": "python",
        ".js": "javascript",
        ".java": "java",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".go": "go",
        ".ts": "typescript",
        ".rs": "rust"
    }
    return mapping.get(ext, "unknown")

# --- NEW FUNCTION ---
def generate_tree_structure(startpath: str, max_depth: int = 3) -> str:
    """
    Generates a visual directory tree string.
    """
    # Validate startpath
    if not startpath or not os.path.exists(startpath):
        return f"Tree structure unavailable: invalid path ({startpath})"
    
    tree_lines = []
    
    # Calculate base depth to calculate relative level
    base_depth = startpath.rstrip(os.path.sep).count(os.path.sep)
    
    for root, dirs, files in os.walk(startpath):
        # Filter out hidden folders and git
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
        files = [f for f in files if not f.startswith('.') and not f.endswith('.pyc')]
        
        # Calculate current level
        level = root.count(os.path.sep) - base_depth
        
        # Stop if max depth reached
        if level > max_depth:
            continue
            
        indent = '│   ' * level
        basename = os.path.basename(root)
        
        # Don't print the root path itself as a sub-item, print contents
        if level == 0:
            tree_lines.append(f"📂 {basename}/")
        else:
            tree_lines.append(f"{indent}├── {basename}/")
        
        subindent = '│   ' * (level + 1)
        
        # Limit file display to avoid spamming for large repos
        for i, f in enumerate(files):
            if i > 15: # If more than 15 files in a folder, truncate
                tree_lines.append(f"{subindent}... ({len(files) - 15} more files)")
                break
            tree_lines.append(f"{subindent}├── {f}")
            
    return "\n".join(tree_lines)