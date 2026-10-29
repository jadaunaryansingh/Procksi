"""
Recommendation Generator for Security Issues

This module generates actionable security recommendations based on
detected secret leaks and missing best practices.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional


@dataclass
class Recommendation:
    """A security recommendation with action items."""
    title: str
    description: str
    severity: str  # "critical", "high", "medium", "low"
    category: str  # "secrets", "best_practices"
    action_items: List[str]
    code_example: Optional[str] = None
    documentation_link: Optional[str] = None
    priority: int = 5  # 1-10, higher = more urgent


# Secret leak recommendation templates (student-friendly language)
SECRET_RECOMMENDATIONS: Dict[str, Dict] = {
    "AWS Access Key": {
        "title": "⚠️ AWS Access Key Found in Code",
        "description": "Your code contains an AWS access key. This is like leaving your house key under the doormat - anyone can find it and access your AWS account!",
        "action_items": [
            "Delete this key from AWS immediately (go to AWS IAM console)",
            "Create a new key and store it in a .env file (never commit this file!)",
            "Add .env to your .gitignore file so it won't be uploaded",
            "Use environment variables to load the key in your code",
            "Remove the key from all previous commits in git history"
        ],
        "documentation_link": "https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html",
        "priority": 10
    },
    "AWS Secret": {
        "title": "⚠️ AWS Secret Key Found in Code",
        "description": "Your AWS secret key is visible in your code. This is a serious security risk - it's like posting your password online!",
        "action_items": [
            "Delete this secret key from AWS right now (AWS IAM console)",
            "Create a new secret key and save it in a .env file",
            "Check AWS CloudTrail to see if anyone used your key",
            "Never put secret keys directly in your code",
            "Use environment variables instead"
        ],
        "documentation_link": "https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html",
        "priority": 10
    },
    "Generic Private Key": {
        "title": "🔑 Private Key Found in Code",
        "description": "You have a private key (like an SSH key) in your code. Private keys should always be kept secret!",
        "action_items": [
            "Generate a new key pair to replace this one",
            "Store private keys in a secure location (not in your code)",
            "Add *.pem and *.key files to .gitignore",
            "Use SSH agent or a password manager for keys",
            "Remove the key from your git history"
        ],
        "priority": 10
    },
    "OpenAI API Key": {
        "title": "🤖 OpenAI API Key Found in Code",
        "description": "Your OpenAI API key is in your code. Anyone who finds this can use your account and you'll be charged for their usage!",
        "action_items": [
            "Delete this API key from your OpenAI dashboard immediately",
            "Create a new API key",
            "Store the new key in a .env file (don't commit it!)",
            "Check your OpenAI usage to see if anyone used your key",
            "Set spending limits in your OpenAI dashboard"
        ],
        "documentation_link": "https://platform.openai.com/docs/api-reference/authentication",
        "priority": 9
    },
    "GitHub Token": {
        "title": "🔐 GitHub Token Found in Code",
        "description": "Your GitHub personal access token is visible in your code. This gives access to your repositories!",
        "action_items": [
            "Delete this token from GitHub settings right away",
            "Create a new token with only the permissions you need",
            "For GitHub Actions, use GitHub secrets instead",
            "Check your repository access logs for suspicious activity",
            "Enable two-factor authentication on your GitHub account"
        ],
        "documentation_link": "https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens",
        "priority": 9
    },
    "JWT Token": {
        "title": "🎫 JWT Token Found in Code",
        "description": "You have a JWT (authentication token) in your code. This can be used to impersonate users in your application!",
        "action_items": [
            "Invalidate this token immediately (add to blacklist or change signing key)",
            "Never put JWT tokens in your code",
            "Make tokens expire quickly (like after 15 minutes)",
            "Use refresh tokens for longer sessions",
            "Store tokens securely on the client side (httpOnly cookies)"
        ],
        "priority": 8
    },
    "default": {
        "title": "🔒 Secret Found in Code",
        "description": "Your code contains sensitive information that should be kept private. This is a security risk!",
        "action_items": [
            "Change or delete this credential immediately",
            "Move all secrets to environment variables (.env file)",
            "Add .env to .gitignore so it won't be uploaded",
            "Use a secrets manager for production (like AWS Secrets Manager)",
            "Clean up your git history to remove the secret"
        ],
        "priority": 8
    }
}


def generate_secret_recommendations(secrets: List[Dict]) -> List[Recommendation]:
    """
    Generate recommendations for detected secret leaks.
    
    Args:
        secrets: List of detected secret leaks
        
    Returns:
        List of recommendations
    """
    recommendations = []
    
    # Group secrets by type
    secrets_by_type: Dict[str, List[Dict]] = {}
    for secret in secrets:
        secret_type = secret.get("type", "Unknown")
        if secret_type not in secrets_by_type:
            secrets_by_type[secret_type] = []
        secrets_by_type[secret_type].append(secret)
    
    # Generate recommendation for each type
    for secret_type, secret_list in secrets_by_type.items():
        template = SECRET_RECOMMENDATIONS.get(secret_type, SECRET_RECOMMENDATIONS["default"])
        
        # Adjust severity based on confidence
        avg_confidence = sum(s.get("confidence", 1.0) for s in secret_list) / len(secret_list)
        if avg_confidence < 0.5:
            severity = "medium"
        else:
            severity = "critical"
        
        description = f"{template['description']} Found in {len(secret_list)} location(s)."
        
        recommendations.append(Recommendation(
            title=template["title"],
            description=description,
            severity=severity,
            category="secrets",
            action_items=template["action_items"],
            documentation_link=template.get("documentation_link"),
            priority=template["priority"]
        ))
    
    return recommendations


def generate_practice_recommendations(practices: List) -> List[Recommendation]:
    """
    Generate recommendations for missing best practices.
    
    Args:
        practices: List of BestPracticeResult objects
        
    Returns:
        List of recommendations
    """
    recommendations = []
    
    for practice in practices:
        # Only generate recommendations for missing or partial implementations
        if practice.status == "implemented":
            continue
        
        # Determine priority based on severity and status
        priority_map = {
            "critical": 9 if practice.status == "missing" else 7,
            "high": 7 if practice.status == "missing" else 5,
            "medium": 5 if practice.status == "missing" else 3,
            "low": 3 if practice.status == "missing" else 2
        }
        priority = priority_map.get(practice.severity, 5)
        
        # Build description
        if practice.status == "missing":
            description = f"{practice.practice_name} is not implemented in this codebase. {practice.recommendation}"
        else:  # partial
            description = f"{practice.practice_name} is only partially implemented (found in {len(practice.files_found)} file(s)). {practice.recommendation}"
        
        # Generate action items
        action_items = [
            practice.recommendation,
            "Review the code example below for implementation guidance",
            f"Implement {practice.practice_name} across all relevant endpoints/modules"
        ]
        
        if practice.status == "partial":
            action_items.append(f"Extend implementation from {', '.join(practice.files_found[:2])}")
        
        recommendations.append(Recommendation(
            title=f"Implement {practice.practice_name}",
            description=description,
            severity=practice.severity,
            category="best_practices",
            action_items=action_items,
            code_example=practice.code_example,
            priority=priority
        ))
    
    return recommendations


def prioritize_recommendations(recommendations: List[Recommendation]) -> List[Recommendation]:
    """
    Sort recommendations by priority (highest first).
    
    Args:
        recommendations: List of recommendations
        
    Returns:
        Sorted list of recommendations
    """
    return sorted(recommendations, key=lambda r: r.priority, reverse=True)


def generate_recommendations(secrets: List[Dict], practices: List) -> List[Recommendation]:
    """
    Generate all security recommendations.
    
    Args:
        secrets: List of detected secret leaks
        practices: List of BestPracticeResult objects
        
    Returns:
        Prioritized list of all recommendations
    """
    all_recommendations = []
    
    # Generate secret recommendations
    if secrets:
        all_recommendations.extend(generate_secret_recommendations(secrets))
    
    # Generate practice recommendations
    if practices:
        all_recommendations.extend(generate_practice_recommendations(practices))
    
    # Prioritize and return
    return prioritize_recommendations(all_recommendations)
