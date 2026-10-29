"""
Best Practices Detector for Security Analysis

This module detects the presence or absence of security best practices
in a codebase by scanning for common security patterns and libraries.
"""

import os
import re
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class BestPracticeResult:
    """Result of a security best practice check."""
    practice_name: str
    status: str  # "implemented", "missing", "partial"
    severity: str  # "critical", "high", "medium", "low"
    files_found: List[str]
    recommendation: str
    code_example: str = ""
    detection_patterns: List[str] = None


# Detection patterns for each security practice
BEST_PRACTICES_PATTERNS: Dict[str, Dict] = {
    "Rate Limiting": {
        "severity": "high",
        "patterns": [
            r"from\s+flask_limiter\s+import",
            r"@limiter\.limit",
            r"express-rate-limit",
            r"rateLimit\(",
            r"@RateLimit",
            r"rate_limit",
        ],
        "recommendation": "Add rate limiting to prevent people from spamming your API with too many requests",
        "code_example": """# Example: Limit API requests to prevent abuse
from flask_limiter import Limiter

# Allow max 50 requests per hour from each user
limiter = Limiter(app, default_limits=["50 per hour"])

@app.route("/api/data")
@limiter.limit("10 per minute")  # Extra limit for this endpoint
def get_data():
    return {"data": "..."}"""
    },
    "Authentication": {
        "severity": "critical",
        "patterns": [
            r"from\s+flask_jwt_extended\s+import",
            r"@jwt_required",
            r"passport\.authenticate",
            r"jwt\.sign",
            r"jwt\.verify",
            r"@require_auth",
            r"authenticate\(",
            r"OAuth",
            r"session\[",
        ],
        "recommendation": "Add user login/authentication so only authorized users can access your app",
        "code_example": """# Example: Require login to access protected pages
from flask_jwt_extended import jwt_required, get_jwt_identity

@app.route("/my-account")
@jwt_required()  # User must be logged in
def my_account():
    user_id = get_jwt_identity()  # Get who's logged in
    return {"user": user_id}"""
    },
    "Authorization": {
        "severity": "critical",
        "patterns": [
            r"@require_permission",
            r"@authorize",
            r"check_permission",
            r"has_permission",
            r"@role_required",
            r"authorize\(",
            r"can\(",
            r"ability\.can",
        ],
        "recommendation": "Check user permissions before allowing actions (e.g., only admins can delete data)",
        "code_example": """# Example: Only allow admins to delete users
def require_admin(f):
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            return {"error": "Admin access required"}, 403
        return f(*args, **kwargs)
    return wrapper

@app.route("/delete-user")
@require_admin  # Only admins can use this
def delete_user():
    pass"""
    },
    "Input Validation": {
        "severity": "high",
        "patterns": [
            r"from\s+pydantic\s+import",
            r"from\s+marshmallow\s+import",
            r"validator\(",
            r"validate\(",
            r"sanitize",
            r"joi\.validate",
            r"express-validator",
            r"@validate",
        ],
        "recommendation": "Check and clean user input to prevent malicious data from breaking your app",
        "code_example": """# Example: Validate user input before using it
from pydantic import BaseModel, validator

class UserInput(BaseModel):
    email: str
    age: int
    
    @validator('email')
    def check_email(cls, v):
        if '@' not in v:
            raise ValueError('Please enter a valid email')
        return v
    
    @validator('age')
    def check_age(cls, v):
        if v < 0 or v > 150:
            raise ValueError('Age must be between 0 and 150')
        return v"""
    },
    "CORS Configuration": {
        "severity": "medium",
        "patterns": [
            r"from\s+flask_cors\s+import",
            r"CORS\(",
            r"cors\(",
            r"Access-Control-Allow-Origin",
            r"@cross_origin",
            r"app\.use\(cors",
        ],
        "recommendation": "Set up CORS to control which websites can access your API",
        "code_example": """# Example: Only allow your website to access the API
from flask_cors import CORS

CORS(app, resources={
    r"/api/*": {
        "origins": ["https://your-website.com"],  # Only this site can access
        "methods": ["GET", "POST"],  # Only these methods allowed
    }
})"""
    },
    "Security Headers": {
        "severity": "medium",
        "patterns": [
            r"helmet\(",
            r"Content-Security-Policy",
            r"X-Frame-Options",
            r"X-Content-Type-Options",
            r"Strict-Transport-Security",
            r"secure_headers",
            r"@secure_headers",
        ],
        "recommendation": "Add security headers to protect users from common web attacks",
        "code_example": """# Example: Add security headers to all responses
@app.after_request
def add_security_headers(response):
    # Prevent clickjacking (your site in an iframe)
    response.headers['X-Frame-Options'] = 'DENY'
    # Prevent MIME type sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Force HTTPS
    response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    return response"""
    },
    "SQL Injection Prevention": {
        "severity": "critical",
        "patterns": [
            r"\.execute\([^,]+,\s*\(",  # Parameterized queries
            r"\.execute\([^,]+,\s*\[",
            r"\.execute\([^,]+,\s*\{",
            r"PreparedStatement",
            r"\.query\([^,]+,\s*\[",
            r"from\s+sqlalchemy\s+import",
            r"db\.session",
        ],
        "recommendation": "Use safe database queries to prevent SQL injection attacks (hackers can't steal your data)",
        "code_example": """# Example: Safe way to query database
# ❌ DANGEROUS - Don't do this:
# query = f"SELECT * FROM users WHERE id = {user_id}"

# ✅ SAFE - Do this instead:
cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))

# Or use an ORM (even safer):
user = db.session.query(User).filter_by(id=user_id).first()"""
    },
    "XSS Prevention": {
        "severity": "high",
        "patterns": [
            r"escape\(",
            r"DOMPurify",
            r"sanitize-html",
            r"bleach\.clean",
            r"html\.escape",
            r"Markup\.escape",
            r"autoescape",
        ],
        "recommendation": "Clean user input before displaying it to prevent XSS attacks (malicious scripts)",
        "code_example": """# Example: Escape user input before showing it
from markupsafe import escape

# User submits: <script>alert('hacked!')</script>
user_comment = request.form['comment']

# Clean it before displaying
safe_comment = escape(user_comment)
# Result: &lt;script&gt;alert('hacked!')&lt;/script&gt;
# Now it's just text, not executable code!"""
    },
    "CSRF Protection": {
        "severity": "high",
        "patterns": [
            r"csrf_token",
            r"CSRFProtect",
            r"@csrf_exempt",
            r"csurf\(",
            r"SameSite",
            r"csrf_protect",
        ],
        "recommendation": "Add CSRF tokens to forms to prevent fake form submissions from other websites",
        "code_example": """# Example: Protect forms with CSRF tokens
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect(app)

# In your HTML form:
<form method="post">
    {{ csrf_token() }}  <!-- This token proves the form is real -->
    <input name="email" type="email">
    <button type="submit">Submit</button>
</form>"""
    },
    "Password Hashing": {
        "severity": "critical",
        "patterns": [
            r"bcrypt",
            r"argon2",
            r"pbkdf2",
            r"scrypt",
            r"generate_password_hash",
            r"check_password_hash",
            r"hashpw",
        ],
        "recommendation": "Hash passwords before storing them (never store plain text passwords!)",
        "code_example": """# Example: Safely store passwords
from bcrypt import hashpw, gensalt, checkpw

# When user signs up:
user_password = request.form.get('password')  # Get from user input
hashed = hashpw(user_password.encode('utf-8'), gensalt())
# Store 'hashed' in database, NOT the plain password!

# When user logs in:
if checkpw(user_password.encode('utf-8'), hashed):
    print("Password correct! ✓")
else:
    print("Wrong password ✗")"""
    },
}


def detect_best_practices(repo_path: str) -> List[BestPracticeResult]:
    """
    Scan repository for security best practices implementation.
    
    Args:
        repo_path: Absolute path to repository root
        
    Returns:
        List of best practice check results
    """
    if not repo_path or not os.path.exists(repo_path):
        return []
    
    results = []
    
    # Track which files contain which patterns
    practice_files: Dict[str, List[str]] = {
        practice: [] for practice in BEST_PRACTICES_PATTERNS.keys()
    }
    
    # Scan files
    for root, _, files in os.walk(repo_path):
        # Skip common non-code directories
        if any(skip in root for skip in ["node_modules", ".git", "dist", "build", "__pycache__", ".venv", "venv"]):
            continue
        
        for file in files:
            # Only scan code files
            if not file.endswith(('.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rb', '.php')):
                continue
            
            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    
                    # Check each practice
                    for practice_name, practice_info in BEST_PRACTICES_PATTERNS.items():
                        for pattern in practice_info["patterns"]:
                            if re.search(pattern, content, re.IGNORECASE):
                                relative_path = file_path.replace(repo_path, "").lstrip(os.sep)
                                if relative_path not in practice_files[practice_name]:
                                    practice_files[practice_name].append(relative_path)
                                break  # Found in this file, move to next practice
            except Exception:
                continue
    
    # Generate results
    for practice_name, practice_info in BEST_PRACTICES_PATTERNS.items():
        files_found = practice_files[practice_name]
        
        if len(files_found) >= 2:
            status = "implemented"
        elif len(files_found) == 1:
            status = "partial"
        else:
            status = "missing"
        
        results.append(BestPracticeResult(
            practice_name=practice_name,
            status=status,
            severity=practice_info["severity"],
            files_found=files_found,
            recommendation=practice_info["recommendation"],
            code_example=practice_info["code_example"],
            detection_patterns=practice_info["patterns"]
        ))
    
    return results
