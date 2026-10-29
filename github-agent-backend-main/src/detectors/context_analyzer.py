"""
Context Analyzer for Code-Aware Secret Detection

This module analyzes code context around potential secrets to determine
if they are likely false positives based on file type, variable names,
and surrounding code patterns.
"""

import re
from dataclasses import dataclass
from typing import List, Optional

# Test file indicators
TEST_FILE_PATTERNS = [
    r"test_",
    r"_test\.",
    r"\.test\.",
    r"\.spec\.",
    r"__tests__",
    r"/tests?/",
    r"spec/",
]

# Example/template file indicators
EXAMPLE_FILE_PATTERNS = [
    r"example",
    r"sample",
    r"template",
    r"\.example$",
    r"\.sample$",
    r"\.template$",
    r"demo",
]

# Placeholder variable name patterns
PLACEHOLDER_VARIABLE_PATTERNS = [
    r"example_",
    r"dummy_",
    r"test_",
    r"sample_",
    r"YOUR_",
    r"REPLACE_",
    r"CHANGE_",
    r"placeholder",
    r"mock_",
    r"fake_",
]


@dataclass
class ContextInfo:
    """Information about the context where a potential secret was found."""
    is_test_file: bool
    is_example_file: bool
    is_commented: bool
    variable_name: Optional[str]
    is_placeholder_variable: bool
    confidence_adjustment: float  # Multiplier for confidence score (0.0-1.0)


def is_test_file(file_path: str) -> bool:
    """
    Check if a file path indicates a test file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if file appears to be a test file
    """
    if not file_path:
        return False
    
    file_path_lower = file_path.lower()
    
    for pattern in TEST_FILE_PATTERNS:
        if re.search(pattern, file_path_lower):
            return True
    
    return False


def is_example_file(file_path: str) -> bool:
    """
    Check if a file path indicates an example/template file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if file appears to be an example or template
    """
    if not file_path:
        return False
    
    file_path_lower = file_path.lower()
    
    for pattern in EXAMPLE_FILE_PATTERNS:
        if re.search(pattern, file_path_lower):
            return True
    
    return False


def extract_variable_name(line: str) -> Optional[str]:
    """
    Extract variable name from a line of code.
    
    Supports common assignment patterns:
    - Python: variable = value
    - JavaScript: const/let/var variable = value
    - Environment: VARIABLE=value
    
    Args:
        line: Line of code to analyze
        
    Returns:
        Variable name if found, None otherwise
    """
    if not line:
        return None
    
    # Remove leading/trailing whitespace
    line = line.strip()
    
    # Python/JavaScript assignment: variable = value
    match = re.search(r'(\w+)\s*=', line)
    if match:
        return match.group(1)
    
    # JavaScript const/let/var: const variable = value
    match = re.search(r'(?:const|let|var)\s+(\w+)\s*=', line)
    if match:
        return match.group(1)
    
    # Environment variable: VARIABLE=value
    match = re.search(r'^(\w+)=', line)
    if match:
        return match.group(1)
    
    # Dictionary/object key: "key": value or 'key': value
    match = re.search(r'["\'](\w+)["\']\s*:', line)
    if match:
        return match.group(1)
    
    return None


def is_placeholder_variable(var_name: str) -> bool:
    """
    Check if a variable name indicates a placeholder.
    
    Args:
        var_name: Variable name to check
        
    Returns:
        True if variable name suggests placeholder/test data
    """
    if not var_name:
        return False
    
    var_name_lower = var_name.lower()
    
    for pattern in PLACEHOLDER_VARIABLE_PATTERNS:
        if re.search(pattern, var_name_lower):
            return True
    
    return False


def analyze_context(
    line: str,
    surrounding_lines: List[str],
    file_path: str
) -> ContextInfo:
    """
    Analyze code context around a potential secret.
    
    Args:
        line: Line containing potential secret
        surrounding_lines: Lines before and after (up to 5 each)
        file_path: Path to file being analyzed
        
    Returns:
        Context information for false positive filtering
    """
    # Check file type
    is_test = is_test_file(file_path)
    is_example = is_example_file(file_path)
    
    # Check if line is commented
    stripped = line.strip()
    is_commented = stripped.startswith(("#", "//", "/*", "*", "'", '"'))
    
    # Extract variable name
    var_name = extract_variable_name(line)
    is_placeholder_var = is_placeholder_variable(var_name) if var_name else False
    
    # Calculate confidence adjustment
    confidence_adjustment = 1.0
    
    # Reduce confidence for test files
    if is_test:
        confidence_adjustment *= 0.5
    
    # Reduce confidence for example files
    if is_example:
        confidence_adjustment *= 0.3
    
    # Reduce confidence for placeholder variables
    if is_placeholder_var:
        confidence_adjustment *= 0.4
    
    # Reduce confidence for commented lines
    if is_commented:
        confidence_adjustment *= 0.2
    
    return ContextInfo(
        is_test_file=is_test,
        is_example_file=is_example,
        is_commented=is_commented,
        variable_name=var_name,
        is_placeholder_variable=is_placeholder_var,
        confidence_adjustment=confidence_adjustment
    )
