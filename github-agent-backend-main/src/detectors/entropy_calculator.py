"""
Entropy Calculator for Secret Validation

This module provides entropy calculation functionality to distinguish real secrets
from placeholder text and decorative patterns. Uses Shannon entropy formula to
measure randomness in detected strings.
"""

import math
from typing import Dict

# Entropy thresholds by secret type
# Higher entropy = more random = more likely to be a real secret
ENTROPY_THRESHOLDS: Dict[str, float] = {
    "AWS Access Key": 3.5,
    "AWS Secret": 4.0,
    "Generic API Key": 3.8,
    "Password": 3.0,
    "JWT Token": 4.5,
    "Google API Key": 3.8,
    "Generic Private Key": 2.5,  # Lower threshold for structured keys
    "OpenAI API Key": 4.0,
    "GitHub Token": 4.0,
    "Stripe Key": 4.0,
    "Hardcoded Password": 3.0,
    "DB Connection String": 3.5,
}


def calculate_entropy(text: str) -> float:
    """
    Calculate Shannon entropy of a string.
    
    Shannon entropy formula: H(X) = -Σ(p(x) * log2(p(x)))
    where p(x) is the probability of character x appearing in the string.
    
    Args:
        text: Input string to analyze
        
    Returns:
        Entropy value (higher = more random, typically 0-8 for text)
        Returns 0.0 for empty strings
    """
    if not text:
        return 0.0
    
    # Count character frequencies
    char_counts: Dict[str, int] = {}
    for char in text:
        char_counts[char] = char_counts.get(char, 0) + 1
    
    # Calculate entropy
    text_length = len(text)
    entropy = 0.0
    
    for count in char_counts.values():
        probability = count / text_length
        entropy -= probability * math.log2(probability)
    
    return entropy


def meets_entropy_threshold(text: str, secret_type: str) -> bool:
    """
    Check if a string meets the entropy threshold for its secret type.
    
    Args:
        text: String to validate
        secret_type: Type of secret (must match ENTROPY_THRESHOLDS keys)
        
    Returns:
        True if entropy meets or exceeds threshold, False otherwise
    """
    if not text:
        return False
    
    threshold = ENTROPY_THRESHOLDS.get(secret_type, 3.0)  # Default threshold
    actual_entropy = calculate_entropy(text)
    
    return actual_entropy >= threshold


def validate_aws_secret_uniqueness(text: str) -> bool:
    """
    Validate AWS secret has sufficient unique characters.
    
    AWS secrets should have high character diversity to avoid matching
    decorative text like "========================================".
    
    Args:
        text: String to validate
        
    Returns:
        True if string has at least 15 unique characters
    """
    if not text:
        return False
    
    unique_chars = len(set(text))
    return unique_chars >= 15


def validate_aws_access_key_uniqueness(text: str) -> bool:
    """
    Validate AWS access key has sufficient unique characters.
    
    Args:
        text: String to validate
        
    Returns:
        True if string has at least 12 unique characters
    """
    if not text:
        return False
    
    unique_chars = len(set(text))
    return unique_chars >= 12
