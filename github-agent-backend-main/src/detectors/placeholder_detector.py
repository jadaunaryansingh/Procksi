"""
Placeholder Detector for False Positive Filtering

This module detects placeholder patterns in strings to filter out example
configurations, template values, and dummy data from secret detection results.
"""

import re
from typing import List

# Placeholder patterns that indicate example/dummy values
PLACEHOLDER_PATTERNS: List[str] = [
    r"YOUR_",
    r"REPLACE_",
    r"CHANGE_",
    r"xxx+",  # Multiple x's
    r"example",
    r"dummy",
    r"test[_-]",
    r"sample",
    r"placeholder",
    r"<[^>]+>",  # Angle bracket placeholders like <API_KEY>
    r"\{[^}]+\}",  # Curly brace placeholders like {API_KEY}
    r"\$\{[^}]+\}",  # Environment variable placeholders like ${API_KEY}
]

# Compile patterns for efficiency
COMPILED_PATTERNS = [re.compile(pattern, re.IGNORECASE) for pattern in PLACEHOLDER_PATTERNS]


def is_placeholder(text: str) -> bool:
    """
    Check if a string contains placeholder patterns.
    
    Args:
        text: String to check
        
    Returns:
        True if string contains any placeholder pattern
    """
    if not text:
        return False
    
    # Check against all compiled patterns
    for pattern in COMPILED_PATTERNS:
        if pattern.search(text):
            return True
    
    return False


def contains_placeholder_pattern(text: str) -> bool:
    """
    Check if a string contains placeholder patterns (alias for is_placeholder).
    
    This function provides a more descriptive name for the same functionality.
    
    Args:
        text: String to check
        
    Returns:
        True if string contains any placeholder pattern
    """
    return is_placeholder(text)
