"""
PDF Report Generator for Team Analysis Reports.
Uses ReportLab for PDF generation.
Modern, visually polished report with all mentor dashboard details.
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, ListFlowable, ListItem, Flowable
)
from io import BytesIO
from datetime import datetime, timedelta
from typing import Dict, Any, List
import html


# ======================== CUSTOM FLOWABLES ========================

class ReportHeaderBand(Flowable):
    """Full-width navy header band for reports."""
    
    def __init__(self, team_name: str, project_name: str = "", repo_url: Any = "",
                 date_str: str = "", health_status: str = "", width: float = None,
                 project_type: str = ""):
        Flowable.__init__(self)
        self.team_name = team_name
        self.project_name = project_name
        
        # Handle multiple URLs
        if isinstance(repo_url, list):
            self.repo_urls = repo_url
        elif isinstance(repo_url, str) and ',' in repo_url:
            self.repo_urls = [u.strip() for u in repo_url.split(',')]
        elif repo_url:
            self.repo_urls = [str(repo_url)]
        else:
            self.repo_urls = []
            
        self.date_str = date_str
        self.health_status = health_status
        self._width = width or (A4[0] - 80)
        self.project_type = project_type
        self.height = 95
    
    def wrap(self, availWidth, availHeight):
        self._width = availWidth
        return (self._width, self.height)
    
    def draw(self):
        c = self.canv
        w, h = self._width, self.height
        
        # Navy background
        c.setFillColor(colors.HexColor('#0f172a'))
        c.roundRect(0, 0, w, h, 8, fill=1, stroke=0)
        
        # Blue accent stripe
        c.setFillColor(colors.HexColor('#2563eb'))
        c.rect(0, 0, w, 4, fill=1, stroke=0)
        
        # Title
        c.setFillColor(colors.HexColor('#94a3b8'))
        c.setFont('Helvetica', 10)
        c.drawString(20, h - 16, "TEAM ANALYSIS REPORT")
        
        # Team name
        c.setFillColor(colors.white)
        c.setFont('Helvetica-Bold', 22)
        c.drawString(20, h - 40, self.team_name[:40])
        
        # Project name
        if self.project_name and self.project_name != self.team_name:
            c.setFillColor(colors.HexColor('#93c5fd'))
            c.setFont('Helvetica', 11)
            c.drawString(20, h - 56, f"Project: {self.project_name[:50]}")
            
        # Project type
        c.setFillColor(colors.HexColor('#38bdf8'))
        c.setFont('Helvetica', 10)
        c.drawString(20, h - 72, f"Project Type: {self.project_type}")
        
        # Right side: health status badge
        if self.health_status:
            status_colors = {
                'on_track': ('#16a34a', '#dcfce7'),
                'at_risk': ('#ca8a04', '#fef9c3'),
                'critical': ('#dc2626', '#fee2e2'),
            }
            status_key = self.health_status.lower().replace(' ', '_')
            fg, bg = status_colors.get(status_key, ('#64748b', '#f1f5f9'))
            
            label = self.health_status.replace('_', ' ').title()
            tw = c.stringWidth(label, 'Helvetica-Bold', 9) + 16
            bx = w - tw - 20
            
            c.setFillColor(colors.HexColor(bg))
            c.roundRect(bx, h - 44, tw, 20, 4, fill=1, stroke=0)
            c.setFillColor(colors.HexColor(fg))
            c.setFont('Helvetica-Bold', 9)
            c.drawCentredString(bx + tw / 2, h - 38, label)
        
        # Bottom: repo url and date
        c.setFillColor(colors.HexColor('#64748b'))
        c.setFont('Helvetica', 8)
        if self.repo_urls:
            if len(self.repo_urls) == 1:
                c.drawString(20, 10, self.repo_urls[0][:75])
            else:
                c.drawString(20, 10, f"Multi-Repo Project ({len(self.repo_urls)} repositories)")
        
        if self.date_str:
            c.drawRightString(w - 20, 10, self.date_str)


class ScoreBarRow(Flowable):
    """Horizontal progress bar for a single score metric."""
    
    def __init__(self, label: str, score: float, max_score: float = 100,
                 bar_width: float = None, height: float = 22):
        Flowable.__init__(self)
        self.label = label
        try:
            self.score = float(score)
        except (TypeError, ValueError):
            self.score = 0.0
        try:
            self.max_score = float(max_score)
        except (TypeError, ValueError):
            self.max_score = 100.0
        self._bar_width = bar_width
        self.height = height
    
    def wrap(self, availWidth, availHeight):
        self._bar_width = self._bar_width or (availWidth - 160)
        return (availWidth, self.height)
    
    def _get_color(self) -> tuple:
        if self.score >= 80: return ('#16a34a', '#dcfce7')
        elif self.score >= 60: return ('#ca8a04', '#fef9c3')
        elif self.score >= 40: return ('#ea580c', '#ffedd5')
        else: return ('#dc2626', '#fee2e2')
    
    def draw(self):
        c = self.canv
        fg, bg = self._get_color()
        
        label_w = 110
        bar_x = label_w + 10
        bar_w = self._bar_width or 280
        bar_h = 14
        y = (self.height - bar_h) / 2
        
        # Label
        c.setFillColor(colors.HexColor('#334155'))
        c.setFont('Helvetica', 10)
        c.drawString(0, y + 2, self.label)
        
        # Background bar (track)
        c.setFillColor(colors.HexColor(bg))
        c.roundRect(bar_x, y, bar_w, bar_h, 3, fill=1, stroke=0)
        
        # Filled bar
        fill_w = max(4, (self.score / self.max_score) * bar_w)
        c.setFillColor(colors.HexColor(fg))
        c.roundRect(bar_x, y, fill_w, bar_h, 3, fill=1, stroke=0)
        
        # Score text
        c.setFillColor(colors.HexColor('#0f172a'))
        c.setFont('Helvetica-Bold', 10)
        c.drawString(bar_x + bar_w + 10, y + 2, f"{int(round(self.score))}")
        
        # Rating text
        if self.score >= 80: rating = "Excellent"
        elif self.score >= 60: rating = "Good"
        elif self.score >= 40: rating = "Fair"
        else: rating = "Needs Work"
        
        c.setFillColor(colors.HexColor(fg))
        c.setFont('Helvetica', 7)
        # Position inside the bar if wide enough
        if fill_w > 60:
            c.setFillColor(colors.white)
            c.drawString(bar_x + 6, y + 3, rating)


class SectionHeader(Flowable):
    """Section header with left accent bar."""
    
    def __init__(self, text: str, icon: str = "", color: str = '#2563eb'):
        Flowable.__init__(self)
        self.text = text
        self.icon = icon
        self.color = color
        self.height = 28
    
    def wrap(self, availWidth, availHeight):
        self._width = availWidth
        return (availWidth, self.height)
    
    def draw(self):
        c = self.canv
        
        # Accent bar
        c.setFillColor(colors.HexColor(self.color))
        c.roundRect(0, 2, 4, self.height - 4, 2, fill=1, stroke=0)
        
        # Text
        c.setFillColor(colors.HexColor('#0f172a'))
        c.setFont('Helvetica-Bold', 13)
        label = f"{self.icon} {self.text}" if self.icon else self.text
        c.drawString(14, 8, label)


# ======================== MAIN GENERATOR ========================

class TeamReportPDFGenerator:
    """Generates comprehensive PDF reports for team analysis."""
    
    NAVY = '#0f172a'
    BLUE = '#2563eb'
    SLATE_700 = '#334155'
    SLATE_500 = '#64748b'
    SLATE_200 = '#e2e8f0'
    SLATE_50 = '#f8fafc'
    GREEN = '#16a34a'
    AMBER = '#ca8a04'
    ORANGE = '#ea580c'
    RED = '#dc2626'
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Set up custom paragraph styles."""
        self.styles.add(ParagraphStyle(
            name='RPT_Body',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=6,
            textColor=colors.HexColor(self.SLATE_700),
            leading=14
        ))
        self.styles.add(ParagraphStyle(
            name='RPT_Small',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor(self.SLATE_500),
            leading=12
        ))
        self.styles.add(ParagraphStyle(
            name='RPT_Pro',
            parent=self.styles['Normal'],
            fontSize=10,
            leftIndent=15,
            textColor=colors.HexColor(self.GREEN),
            leading=14
        ))
        self.styles.add(ParagraphStyle(
            name='RPT_Con',
            parent=self.styles['Normal'],
            fontSize=10,
            leftIndent=15,
            textColor=colors.HexColor(self.RED),
            leading=14
        ))
        self.styles.add(ParagraphStyle(
            name='RPT_Feature',
            parent=self.styles['Normal'],
            fontSize=10,
            leftIndent=15,
            textColor=colors.HexColor(self.BLUE),
            leading=14
        ))
        self.styles.add(ParagraphStyle(
            name='RPT_Subsection',
            parent=self.styles['Heading3'],
            fontSize=11,
            spaceBefore=10,
            spaceAfter=6,
            textColor=colors.HexColor(self.SLATE_700),
            fontName='Helvetica-Bold'
        ))
        self.styles.add(ParagraphStyle(
            name='RPT_CommitMsg',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#374151'),
            leftIndent=10,
            leading=12
        ))
        self.styles.add(ParagraphStyle(
            name='RPT_CommitMeta',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#6b7280'),
            leftIndent=10,
            leading=10
        ))
        self.styles.add(ParagraphStyle(
            name='RPT_Footer',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor(self.SLATE_500),
            alignment=1
        ))
    
    # ======================== SCORE INSIGHTS ========================

    # Threshold below which a score is considered "low" and needs explanation
    LOW_SCORE_THRESHOLD = 50

    # Static knowledge base: for each scoring dimension, why it might be low
    # and what students can do to improve.
    SCORE_INSIGHTS_DB: Dict[str, Dict[str, Any]] = {
        'Quality': {
            'what_it_measures': 'Code readability, structure, naming conventions, and maintainability index.',
            'common_reasons': [
                'Poor variable/function naming (single-letter names, unclear abbreviations)',
                'Lack of code comments or docstrings',
                'Very long functions with high complexity',
                'Duplicated code blocks instead of reusable functions',
                'Inconsistent coding style (mixed indentation, formatting)',
            ],
            'how_to_improve': [
                'Use descriptive variable and function names that explain intent',
                'Break large functions into smaller, focused functions (< 30 lines each)',
                'Add docstrings to all public functions and classes',
                'Use a linter (ESLint, Pylint, Flake8) to enforce consistent style',
                'Eliminate code duplication by extracting shared logic into utility functions',
            ],
        },
        'Security': {
            'what_it_measures': 'Presence of leaked secrets, security best practices, and vulnerability patterns.',
            'common_reasons': [
                'API keys, passwords, or tokens committed to the repository',
                'Missing .gitignore entries for .env files',
                'No input validation or sanitization',
                'Using HTTP instead of HTTPS for API calls',
                'Hardcoded credentials in source code',
            ],
            'how_to_improve': [
                'Never commit secrets — use environment variables and .env files',
                'Add .env, .env.local, and secret files to .gitignore immediately',
                'Use tools like git-secrets or gitleaks to scan before committing',
                'Validate and sanitize all user inputs on both client and server',
                'Rotate any leaked credentials and remove them from git history',
            ],
        },
        'Originality': {
            'what_it_measures': 'How much of the code appears to be human-written vs AI-generated or copied.',
            'common_reasons': [
                'Large portions of code generated by AI tools (ChatGPT, Copilot) without modification',
                'Copy-pasting boilerplate from tutorials without customization',
                'Using template projects without significant changes',
                'High similarity with publicly available repositories',
            ],
            'how_to_improve': [
                'Write core logic yourself — use AI only for reference, not copy-paste',
                'Customize boilerplate and templates to match your project needs',
                'Add unique features and business logic specific to your problem statement',
                'Document your thought process in commit messages to show understanding',
                'Refactor AI-generated code to match your coding style and project architecture',
            ],
        },
        'Effort': {
            'what_it_measures': 'Commit frequency, consistency, lines of code, and contribution distribution.',
            'common_reasons': [
                'Very few commits (bulk commits instead of incremental work)',
                'Most work done in 1-2 days instead of spread across the timeline',
                'Uneven contribution — one member doing most of the work',
                'Large gaps between commits indicating last-minute work',
                'Low lines of code relative to project complexity',
            ],
            'how_to_improve': [
                'Commit regularly — aim for daily or every-other-day commits',
                'Make small, focused commits (50-200 lines) instead of massive bulk commits',
                'Distribute work evenly across all team members',
                'Start working early and maintain a steady pace throughout the timeline',
                'Use branches for features and merge frequently to show continuous progress',
            ],
        },
        'Implementation': {
            'what_it_measures': 'How well the stated features are actually implemented and working.',
            'common_reasons': [
                'Features listed in README but not actually implemented in code',
                'Incomplete CRUD operations or broken API endpoints',
                'UI exists but has no functional backend integration',
                'Missing error handling and edge case coverage',
                'Core functionality is hardcoded or uses mock data',
            ],
            'how_to_improve': [
                'Ensure every feature mentioned in your README has working code',
                'Complete full user flows — from UI input to database storage to display',
                'Add proper error handling and loading states',
                'Replace mock/hardcoded data with actual backend integration',
                'Test each feature end-to-end before submission',
            ],
        },
        'Engineering': {
            'what_it_measures': 'Use of engineering best practices: testing, CI/CD, Docker, environment configs.',
            'common_reasons': [
                'No test files found in the repository',
                'No CI/CD pipeline (GitHub Actions, etc.)',
                'No Docker or containerization setup',
                'Missing environment configuration files',
                'No package manager lock files (package-lock.json, Pipfile.lock)',
            ],
            'how_to_improve': [
                'Add at least basic unit tests for core functions (pytest, jest, etc.)',
                'Set up a simple GitHub Actions workflow for automated testing',
                'Create a Dockerfile and docker-compose.yml for easy deployment',
                'Use .env files with a .env.example template for configuration',
                'Add proper dependency management (requirements.txt, package.json)',
            ],
        },
        'Organization': {
            'what_it_measures': 'Project folder structure, separation of concerns, and code architecture.',
            'common_reasons': [
                'All code in a single file or flat directory structure',
                'No separation between frontend and backend code',
                'Missing standard project files (README, .gitignore, LICENSE)',
                'Mixed concerns — database logic inside UI components',
                'No clear module or package organization',
            ],
            'how_to_improve': [
                'Follow standard project layouts for your framework (e.g., MVC, feature-based)',
                'Separate code into logical folders: src/, tests/, docs/, config/',
                'Keep frontend and backend in distinct directories',
                'Create a clear README with setup instructions and project structure',
                'Use separate files for routes, models, services, and utilities',
            ],
        },
        'Documentation': {
            'what_it_measures': 'README quality, inline comments, API docs, and setup instructions.',
            'common_reasons': [
                'README is missing or contains only the project title',
                'No setup/installation instructions',
                'No API documentation or endpoint descriptions',
                'Missing inline comments explaining complex logic',
                'No screenshots or demo of the working project',
            ],
            'how_to_improve': [
                'Write a comprehensive README with: description, features, tech stack, setup steps',
                'Add screenshots or GIFs demonstrating the working application',
                'Document API endpoints with request/response examples',
                'Include a "How to Run" section with step-by-step instructions',
                'Add inline comments for complex algorithms and business logic',
            ],
        },
        'Architecture': {
            'what_it_measures': 'System design, design patterns, and structural organization.',
            'common_reasons': [
                'No clear architectural pattern (MVC, layered, microservices)',
                'Tight coupling between components',
                'No separation of data access, business logic, and presentation',
                'Missing dependency injection or configuration management',
                'Monolithic design without modular boundaries',
            ],
            'how_to_improve': [
                'Follow an established architectural pattern (MVC, Clean Architecture)',
                'Separate concerns: controllers, services, repositories, models',
                'Use dependency injection instead of hard-coded dependencies',
                'Create clear API contracts between frontend and backend',
                'Design for testability — isolate business logic from I/O operations',
            ],
        },
        'Total Score': {
            'what_it_measures': 'Weighted average of all scoring dimensions.',
            'common_reasons': [
                'Multiple scoring dimensions are below acceptable levels',
                'Critical areas like Implementation (25%) or Originality (20%) are very low',
                'Fake commits or repository hygiene issues causing score penalties',
            ],
            'how_to_improve': [
                'Focus on the lowest-scoring dimensions first for maximum impact',
                'Implementation (25% weight) and Originality (20%) have the highest impact',
                'Clean up fake commits and repository hygiene to remove penalties',
                'Review each dimension\'s feedback below and address systematically',
            ],
        },
        'Deployment': {
            'what_it_measures': 'Whether the project is deployed and accessible online.',
            'common_reasons': [
                'Project is not deployed to any hosting platform',
                'No live URL or demo link provided',
                'Deployment configuration files are missing',
            ],
            'how_to_improve': [
                'Deploy frontend to Vercel, Netlify, or GitHub Pages (free)',
                'Deploy backend to Railway, Render, or Fly.io (free tiers available)',
                'Add the live URL to your README',
                'Include deployment instructions in your documentation',
            ],
        },
        'Test coverage': {
            'what_it_measures': 'Presence and coverage of automated tests.',
            'common_reasons': [
                'No test files found in the repository',
                'Tests exist but cover very few functions',
                'Only manual testing was performed',
            ],
            'how_to_improve': [
                'Add unit tests for core business logic using pytest/jest/JUnit',
                'Aim for at least 30-50% coverage on critical modules',
                'Write integration tests for API endpoints',
                'Use GitHub Actions to run tests automatically on each push',
            ],
        },
    }

    def _get_score_insights(self, report_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate **personalized** insights for low-scoring dimensions.

        Reasons are derived from actual report data (security issues, commit
        patterns, maturity flags, AI %, etc.) — not generic checklists.
        Dimensions with no supporting data are skipped.

        Returns a list of dicts sorted worst-first, each with:
          dimension, score, severity, what_it_measures,
          likely_reasons (data-driven), improvement_steps
        """
        analysis = report_data.get('analysis', {})
        if not analysis:
            return []

        score_items = [
            ('Quality', analysis.get('qualityScore', 0)),
            ('Security', analysis.get('securityScore', 0)),
            ('Originality', analysis.get('originalityScore', 0)),
            ('Architecture', analysis.get('architectureScore', 0)),
            ('Documentation', analysis.get('documentationScore', 0)),
            ('Effort', analysis.get('effortScore', 0)),
            ('Implementation', analysis.get('implementationScore', 0)),
            ('Engineering', analysis.get('engineeringScore', 0)),
        ]

        insights = []

        for dimension, raw_score in score_items:
            score = self._to_float(raw_score, 0.0)
            if score >= self.LOW_SCORE_THRESHOLD or score <= 0:
                continue  # Skip good scores and zeros (not evaluated)

            db_entry = self.SCORE_INSIGHTS_DB.get(dimension, {})
            if not db_entry:
                continue

            # Severity label
            if score < 20:
                severity = 'critical'
            elif score < 40:
                severity = 'needs_work'
            else:
                severity = 'fair'

            # ── Build PERSONALIZED reasons from actual report data ──
            reasons: List[str] = []

            if dimension == 'Security':
                sec = report_data.get('security', {})
                secrets = sec.get('secretsDetected', 0) or 0
                if secrets > 0:
                    reasons.append(f'Your repository has {secrets} leaked secret(s)/credential(s)')
                leaks = sec.get('leaks') or sec.get('issues', [])
                if isinstance(leaks, list):
                    for leak in leaks[:2]:
                        if isinstance(leak, dict):
                            desc = leak.get('description') or leak.get('type', '')
                            fpath = leak.get('file_path') or leak.get('file', '')
                            if desc and fpath:
                                reasons.append(f'Found: {desc} in {fpath}')
                            elif desc:
                                reasons.append(f'Issue: {desc}')
                recs = sec.get('recommendations', [])
                if isinstance(recs, list):
                    for rec in recs[:2]:
                        if isinstance(rec, str) and rec.strip():
                            reasons.append(rec.strip())

            elif dimension == 'Originality':
                ai = report_data.get('aiAnalysis', {})
                ai_pct = self._to_float(ai.get('aiGeneratedPercentage', 0), 0.0)
                if ai_pct > 30:
                    reasons.append(f'{ai_pct:.0f}% of your code was flagged as AI-generated')
                verdict = ai.get('verdict', '')
                if verdict and 'ai' in str(verdict).lower():
                    reasons.append(f'AI verdict: {verdict}')
                risky = report_data.get('riskyFiles', [])
                high_ai_files = [f for f in risky if isinstance(f, dict) and self._to_float(f.get('ai_pct', 0), 0) > 60]
                for rf in high_ai_files[:2]:
                    reasons.append(f'{rf.get("name", "?")} — {rf.get("ai_pct", 0):.0f}% AI-generated')

            elif dimension == 'Effort':
                cq = report_data.get('commitQuality', {})
                total_c = cq.get('totalCommits', 0) or 0
                real_c = cq.get('realCommits', 0) or 0
                fake_c = cq.get('fakeCommits', 0) or 0
                fake_pct = self._to_float(cq.get('fakeCommitPercentage', 0), 0.0)
                health = cq.get('healthStatus', '')

                if total_c > 0 and total_c < 20:
                    reasons.append(f'Only {total_c} total commits — very low development activity')
                if fake_pct > 10:
                    reasons.append(f'{fake_pct:.0f}% of commits ({fake_c}/{total_c}) are fake/low-quality')
                if health and health != 'Healthy':
                    reasons.append(f'Commit health: {health}')

                # Check contributor imbalance
                contributors = report_data.get('commits', {}).get('contributors', [])
                if len(contributors) >= 2:
                    pcts = sorted([self._to_float(c.get('contributionPct', 0), 0) for c in contributors], reverse=True)
                    if pcts[0] > 70:
                        top_name = next((c.get('name', '?') for c in contributors
                                         if self._to_float(c.get('contributionPct', 0), 0) == pcts[0]), '?')
                        reasons.append(f'Uneven contribution — {top_name} made {pcts[0]:.0f}% of all commits')

            elif dimension == 'Implementation':
                ai = report_data.get('aiAnalysis', {})
                func_check = ai.get('functionalityCheck', {})
                completeness = ai.get('completenessAnalysis', {})
                constructive = ai.get('constructiveFeedback', '')

                if isinstance(func_check, dict):
                    working = func_check.get('workingFeatures', [])
                    broken = func_check.get('brokenFeatures', []) or func_check.get('missingFeatures', [])
                    if isinstance(broken, list) and broken:
                        for feat in broken[:2]:
                            feat_text = feat if isinstance(feat, str) else feat.get('name', str(feat))
                            reasons.append(f'Missing/broken feature: {feat_text}')
                    if isinstance(working, list):
                        reasons.append(f'{len(working)} feature(s) verified working, but gaps remain')

                if isinstance(completeness, dict):
                    pct = completeness.get('completionPercentage', 0) or completeness.get('percentage', 0)
                    if pct and pct < 60:
                        reasons.append(f'Only {pct}% of stated features appear complete')

                if constructive and not reasons:
                    # Use a snippet of AI constructive feedback as personalized context
                    snippet = str(constructive)[:150].strip()
                    if snippet:
                        reasons.append(f'AI feedback: "{snippet}…"')

            elif dimension == 'Engineering':
                mat = report_data.get('maturity', {})
                if mat:
                    if not mat.get('hasTests'):
                        reasons.append('No test files detected in your repository')
                    elif mat.get('testFiles', 0) < 3:
                        reasons.append(f'Only {mat.get("testFiles", 0)} test file(s) found — very limited coverage')
                    if not mat.get('hasCI'):
                        reasons.append('No CI/CD pipeline (GitHub Actions, etc.) configured')
                    if not mat.get('hasDocker'):
                        reasons.append('No Docker/containerization setup found')

            elif dimension == 'Documentation':
                mat = report_data.get('maturity', {})
                if mat:
                    if not mat.get('hasReadme'):
                        reasons.append('No README file detected — this is critical')
                metrics = report_data.get('codeMetrics', {})
                if isinstance(metrics, dict):
                    total_files = metrics.get('totalFiles', 0) or 0
                    if total_files > 0 and total_files < 5:
                        reasons.append(f'Very few files ({total_files}) may indicate missing documentation files')

            elif dimension == 'Architecture':
                metrics = report_data.get('codeMetrics', {})
                pattern = metrics.get('architecturePattern', '') if isinstance(metrics, dict) else ''
                if pattern and pattern.lower() in ('unknown', 'none', ''):
                    reasons.append('No recognizable architectural pattern detected')
                elif pattern:
                    reasons.append(f'Detected pattern: {pattern} — but implementation is incomplete')

            elif dimension == 'Quality':
                ai = report_data.get('aiAnalysis', {})
                qi = ai.get('qualityIndicators', {})
                if isinstance(qi, dict):
                    for indicator, value in qi.items():
                        if isinstance(value, str) and len(value) < 120:
                            reasons.append(f'{indicator}: {value}')
                        if len(reasons) >= 3:
                            break
                # Check code metrics for quality hints
                metrics = report_data.get('codeMetrics', {})
                if isinstance(metrics, dict):
                    loc = metrics.get('totalLinesOfCode', 0) or 0
                    files = metrics.get('totalFiles', 0) or 0
                    if files > 0 and loc / max(1, files) > 500:
                        reasons.append(f'Average {loc // max(1, files)} lines/file — files may be too large')

            # ── If no personalized data found, add 1-2 generic fallbacks ──
            if not reasons:
                generic = db_entry.get('common_reasons', [])
                reasons = generic[:2]  # Only top 2 generic, not the full list

            # Skip this dimension if we truly have nothing to say
            if not reasons:
                continue

            insights.append({
                'dimension': dimension,
                'score': round(score, 1),
                'severity': severity,
                'what_it_measures': db_entry.get('what_it_measures', ''),
                'likely_reasons': reasons[:4],
                'improvement_steps': db_entry.get('how_to_improve', [])[:4],
            })

        # Sort by score ascending (worst first)
        insights.sort(key=lambda x: x['score'])

        return insights

    def _build_score_insights_section(self, story: List, report_data: Dict[str, Any]):
        """Add the 'Why Scores Are Low & How to Improve' section to the PDF story."""
        insights = self._get_score_insights(report_data)
        
        if not insights:
            return  # All scores are above threshold — nothing to show
        
        story.append(SectionHeader("Score Analysis & Improvement Guide", "INSIGHTS", self.ORANGE))
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "The following dimensions scored below 50/100. Here's <b>why</b> and <b>how to improve</b>:",
            self.styles['RPT_Body']
        ))
        story.append(Spacer(1, 6))
        
        for insight in insights:
            dimension = insight['dimension']
            score = insight['score']
            severity = insight['severity']
            
            # Severity badge color
            if severity == 'critical':
                sev_color = self.RED
                sev_label = 'CRITICAL'
            elif severity == 'needs_work':
                sev_color = self.ORANGE
                sev_label = 'NEEDS WORK'
            else:
                sev_color = self.AMBER
                sev_label = 'FAIR'
            
            # Dimension header with score and severity
            story.append(Paragraph(
                f"<b>{dimension}</b> — <font color='{sev_color}'><b>{int(round(score))}/100 [{sev_label}]</b></font>",
                self.styles['RPT_Subsection']
            ))
            
            # What it measures
            what = insight.get('what_it_measures', '')
            if what:
                story.append(Paragraph(
                    f"<i>Measures: {what}</i>",
                    self.styles['RPT_Small']
                ))
            
            # Why it's low
            reasons = insight.get('likely_reasons', [])
            if reasons:
                story.append(Paragraph("<b>Why this score is low:</b>", self.styles['RPT_Body']))
                for reason in reasons:
                    safe_reason = html.escape(str(reason))
                    story.append(Paragraph(f"  - {safe_reason}", self.styles['RPT_Con']))
            
            # How to improve
            steps = insight.get('improvement_steps', [])
            if steps:
                story.append(Paragraph("<b>How to improve:</b>", self.styles['RPT_Body']))
                for step in steps:
                    safe_step = html.escape(str(step))
                    story.append(Paragraph(f"  + {safe_step}", self.styles['RPT_Pro']))
            
            story.append(Spacer(1, 8))

    def _get_score_color(self, score: float) -> str:
        if score >= 80: return self.GREEN
        elif score >= 60: return self.AMBER
        elif score >= 40: return self.ORANGE
        else: return self.RED

    def _to_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _sanitize_report_data(self, value: Any) -> Any:
        """Recursively sanitize text for ReportLab's default Helvetica font."""
        if isinstance(value, dict):
            return {k: self._sanitize_report_data(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._sanitize_report_data(v) for v in value]
        if isinstance(value, str):
            # Escape XML/HTML-sensitive chars for Paragraph rendering and normalize to ASCII.
            safe = html.escape(value, quote=False)
            return safe.encode("ascii", "replace").decode("ascii")
        return value
    
    def _create_contributors_table(self, contributors: List[Dict]) -> Table:
        """Create a modern table for contributors."""
        data = [['Contributor', 'Commits', 'Lines Changed', 'Share']]
        
        for contrib in contributors[:10]:
            pct = self._to_float(contrib.get('contributionPct', 0), 0.0)
            name = str(contrib.get('name', 'Unknown') or 'Unknown')[:28]
            commits = int(self._to_float(contrib.get('commits', 0), 0.0))
            additions = int(self._to_float(contrib.get('additions', 0), 0.0))
            deletions = int(self._to_float(contrib.get('deletions', 0), 0.0))
            data.append([
                name,
                str(commits),
                f"+{additions}/-{deletions}",
                f"{pct:.1f}%"
            ])
        
        if not contributors:
            data.append(['No contributors found', '-', '-', '-'])
        
        table = Table(data, colWidths=[2.2*inch, 0.8*inch, 1.2*inch, 0.8*inch])
        
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(self.NAVY)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
            ('TOPPADDING', (0, 0), (-1, 0), 5),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
            ('TOPPADDING', (0, 1), (-1, -1), 3),
            ('LINEBELOW', (0, 0), (-1, -1), 0.3, colors.HexColor('#f1f5f9')),
            ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.HexColor(self.BLUE)),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(self.SLATE_50)]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ])
        
        # Highlight top contributor
        if len(data) > 1:
            style.add('FONTNAME', (0, 1), (0, 1), 'Helvetica-Bold')
            style.add('TEXTCOLOR', (3, 1), (3, 1), colors.HexColor(self.BLUE))
        
        table.setStyle(style)
        return table

    def _create_weekly_marks_table(self, weekly_marks: List[Dict]) -> Table:
        """Create a compact weekly individual marks table for all team members."""
        data = [['Team Member', 'Commits', 'Share', 'Base Mark', 'Penalty', 'Weekly Mark']]

        for row in (weekly_marks or [])[:20]:
            name = str(row.get('name', 'Unknown') or 'Unknown')[:24]
            commits = int(self._to_float(row.get('commits', 0), 0.0))
            share = self._to_float(row.get('contributionPct', 0), 0.0)
            base_mark = self._to_float(row.get('weeklyBaseMark', 0), 0.0)
            penalty = self._to_float(row.get('inactivityPenalty', 0), 0.0)
            weekly_mark = self._to_float(row.get('weeklyIndividualMark', 0), 0.0)

            data.append([
                name,
                str(commits),
                f"{int(round(share))}%",
                str(int(round(base_mark))),
                f"-{int(round(penalty))}",
                str(int(round(weekly_mark))),
            ])

        if not weekly_marks:
            data.append(['No student marks available', '-', '-', '-', '-', '-'])

        table = Table(data, colWidths=[1.8*inch, 0.6*inch, 0.7*inch, 0.8*inch, 0.7*inch, 0.8*inch])
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(self.NAVY)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('LINEBELOW', (0, 0), (-1, -1), 0.3, colors.HexColor('#f1f5f9')),
            ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.HexColor(self.BLUE)),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(self.SLATE_50)]),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ])

        if len(data) > 1:
            style.add('FONTNAME', (0, 1), (0, 1), 'Helvetica-Bold')
            style.add('TEXTCOLOR', (5, 1), (5, 1), colors.HexColor(self.BLUE))

        table.setStyle(style)
        return table
    
    def _create_individual_scores_table(self, individual_scores: List[Dict]) -> Table:
        """Create a table for individual student scores based on contribution metrics."""
        col_headers = ['Student', 'Commits', 'Contribution %', 'Effort', 'Quality', 'Final Score']
        col_widths = [1.8*inch, 0.7*inch, 1.2*inch, 0.8*inch, 0.8*inch, 1.0*inch]
        
        data = [col_headers]
        
        for student in (individual_scores or [])[:20]:
            row = [
                str(student.get('name', 'Unknown'))[:24],
                str(student.get('commits', 0)),
                f"{int(round(self._to_float(student.get('contributionPercentage', 0), 0.0)))}%",
                str(int(round(self._to_float(student.get('effortScore', 0), 0.0)))),
                str(int(round(self._to_float(student.get('qualityScore', 0), 0.0)))),
                str(int(round(self._to_float(student.get('finalScore', 0), 0.0)))),
            ]
            data.append(row)
        
        if not individual_scores:
            data.append(['No student scores available'] + ['-'] * (len(col_headers) - 1))
        
        table = Table(data, colWidths=col_widths)
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(self.NAVY)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('LINEBELOW', (0, 0), (-1, -1), 0.3, colors.HexColor('#f1f5f9')),
            ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.HexColor(self.BLUE)),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(self.SLATE_50)]),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ])

        # Highlight top performer (highest final score)
        if len(data) > 1:
            top_score = max([self._to_float(d[-1], 0.0) for d in data[1:]])
            for i in range(1, len(data)):
                try:
                    if float(data[i][-1]) == top_score:
                        style.add('FONTNAME', (0, i), (0, i), 'Helvetica-Bold')
                        style.add('TEXTCOLOR', (2, i), (-1, i), colors.HexColor(self.BLUE))
                except:
                    pass

        table.setStyle(style)
        return table
    
    def _create_security_issues_table(self, issues: List[Dict]) -> Table:
        """Create a table for security issues."""
        data = [['Type', 'Severity', 'File']]
        
        for issue in issues[:8]:
            issue_type = str(issue.get('type', 'Unknown') or 'Unknown')[:25]
            issue_severity = str(issue.get('severity', 'medium') or 'medium').title()
            issue_file = str(issue.get('file', 'Unknown') or 'Unknown')[:35]
            data.append([
                issue_type,
                issue_severity,
                issue_file
            ])
        
        if not issues:
            data.append(['No issues', '-', '-'])
        
        table = Table(data, colWidths=[1.8*inch, 1*inch, 2.5*inch])
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7f1d1d')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('LINEBELOW', (0, 0), (-1, -1), 0.3, colors.HexColor('#f1f5f9')),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fef2f2')]),
        ])
        table.setStyle(style)
        return table
    
    def _create_risky_files_table(self, risky_files: List[Dict]) -> Table:
        """Create a table for AI/plagiarism risky files."""
        data = [['File', 'AI %', 'Risk Level']]
        
        for rf in risky_files[:8]:
            # Support both legacy keys (file_path/ai_percentage/risk_level) and 
            # actual analysis pipeline keys (name/ai_pct/risk)
            file_name = rf.get('name') or rf.get('file_path') or rf.get('path', 'Unknown')
            ai_pct = self._to_float(rf.get('ai_pct') or rf.get('ai_percentage', 0), 0.0)
            risk_val = self._to_float(rf.get('risk') or rf.get('ai_percentage', 0), 0.0)
            
            # Derive risk level from numeric risk score if no string risk_level
            risk_level = str(rf.get('risk_level', '') or '')
            if not risk_level:
                if risk_val >= 70:
                    risk_level = 'High'
                elif risk_val >= 40:
                    risk_level = 'Medium'
                elif risk_val >= 15:
                    risk_level = 'Low'
                else:
                    risk_level = 'Minimal'
            
            data.append([
                str(file_name)[:40],
                f"{ai_pct:.0f}%",
                str(risk_level)
            ])
        
        if not risky_files:
            data.append(['No risky files', '-', '-'])
        
        table = Table(data, colWidths=[3*inch, 0.8*inch, 1.2*inch])
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#78350f')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('LINEBELOW', (0, 0), (-1, -1), 0.3, colors.HexColor('#f1f5f9')),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('ALIGN', (2, 0), (2, -1), 'CENTER'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fffbeb')]),
        ])
        table.setStyle(style)
        return table
    
    def _create_repo_breakdown_table(self, repos: List[Dict]) -> Table:
        """Create a table summarizing individual repository performance."""
        data = [['Repository', 'Score', 'Files', 'LOC', 'Commits']]
        
        for repo in repos:
            # Prefer explicit repo_name if provided by enriched analyzer
            name = repo.get('repo_name')
            if not name:
                url = str(repo.get('repo_url', 'Unknown'))
                name = url.rstrip('/').split('/')[-1].replace('.git', '')
            
            # Use 'score' key from analyzer breakdown, fallback to 'total_score'
            score = self._to_float(repo.get('score') or repo.get('total_score', 0), 0.0)
            files = int(self._to_float(repo.get('file_count', 0), 0.0))
            loc = int(self._to_float(repo.get('lines_of_code', 0), 0.0))
            commits = int(self._to_float(repo.get('commit_count', 0), 0.0))
            
            # Add tech stack hint if available
            tech_stack = repo.get('tech_stack', [])
            if tech_stack and isinstance(tech_stack, list):
                stack_hint = f" ({', '.join(tech_stack[:2])})"
                display_name = name + stack_hint
            else:
                display_name = name

            data.append([
                display_name,
                f"{score:.1f}",
                str(files),
                f"{loc:,}",
                str(commits)
            ])
            
        table = Table(data, colWidths=[2.2*inch, 0.8*inch, 0.7*inch, 0.8*inch, 0.7*inch])
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(self.NAVY)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('LINEBELOW', (0, 0), (-1, -1), 0.3, colors.HexColor('#f1f5f9')),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(self.SLATE_50)]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ])
        
        for i, repo in enumerate(repos, 1):
            score = self._to_float(repo.get('total_score', 0), 0.0)
            style.add('TEXTCOLOR', (1, i), (1, i), colors.HexColor(self._get_score_color(score)))
            style.add('FONTNAME', (1, i), (1, i), 'Helvetica-Bold')

        table.setStyle(style)
        return table
    
    def generate(self, report_data: Dict[str, Any]) -> bytes:
        """Generate comprehensive PDF report and return as bytes."""
        report_data = self._sanitize_report_data(report_data)
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=40,
            leftMargin=40,
            topMargin=30,
            bottomMargin=30
        )
        
        story = []
        
        # ========== HEADER BAND ==========
        team_name = report_data.get('teamName', 'Unknown Team')
        project_name = report_data.get('projectName', '')
        repo_url = report_data.get('repoUrl', '')
        
        generated_at = report_data.get('generatedAt', datetime.utcnow().isoformat())
        try:
            gen_date = datetime.fromisoformat(generated_at.replace('Z', '+00:00'))
            ist_date = gen_date + timedelta(hours=5, minutes=30)
            formatted_date = ist_date.strftime('%B %d, %Y - %I:%M %p IST')
        except:
            formatted_date = generated_at
        
        health_status = report_data.get('healthStatus', 'on_track')
        project_type = report_data.get('projectType', 'General Project')
        
        story.append(ReportHeaderBand(
            team_name=team_name,
            project_name=project_name,
            repo_url=repo_url,
            date_str=formatted_date,
            health_status=health_status,
            project_type=project_type
        ))
        
        # Team members & problem statement (below header)
        team_members = report_data.get('teamMembers', [])
        if team_members:
            member_names = [m.get('name', 'Unknown') for m in team_members]
            story.append(Spacer(1, 4))
            story.append(Paragraph(
                f"<b>Team Members:</b> {', '.join(member_names)}",
                self.styles['RPT_Small']
            ))
        
        problem_statement = report_data.get('problemStatement', '')
        if problem_statement:
            story.append(Paragraph(
                f"<b>Problem Statement:</b> {problem_statement[:300]}{'...' if len(problem_statement) > 300 else ''}",
                self.styles['RPT_Small']
            ))
        
        story.append(Spacer(1, 8))
        
        # ========== SCORES SECTION (Progress Bars) ==========
        story.append(SectionHeader("Analysis Scores", "SCORES", self.BLUE))
        story.append(Spacer(1, 4))
        
        analysis = report_data.get('analysis', {})
        score_items = [
            ('Total Score', analysis.get('totalScore', 0)),
            ('Quality', analysis.get('qualityScore', 0)),
            ('Security', analysis.get('securityScore', 0)),
            ('Originality', analysis.get('originalityScore', 0)),
            ('Architecture', analysis.get('architectureScore', 0)),
            ('Documentation', analysis.get('documentationScore', 0)),
            ('Effort', analysis.get('effortScore', 0)),
            ('Implementation', analysis.get('implementationScore', 0)),
            ('Engineering', analysis.get('engineeringScore', 0)),
        ]
        
        for name, score in score_items:
             if score > 0:
                story.append(ScoreBarRow(label=name, score=score))
        
        story.append(Spacer(1, 4))

        # ========== SCORE INSIGHTS (Why Low & How to Improve) ==========
        self._build_score_insights_section(story, report_data)

        # ========== REPOSITORY BREAKDOWN (Multi-Repo) ==========
        repo_breakdown = report_data.get('repo_analysis_breakdown') or report_data.get('repoAnalysisBreakdown', [])
        if isinstance(repo_breakdown, list) and len(repo_breakdown) > 1:
            story.append(Paragraph("<b>Per-Repository Breakdown</b>", self.styles['RPT_Subsection']))
            story.append(Spacer(1, 2))
            story.append(self._create_repo_breakdown_table(repo_breakdown))
            story.append(Spacer(1, 6))
        
        # ========== CODE METRICS ==========
        story.append(SectionHeader("Code Metrics", "CODE", '#8b5cf6'))
        story.append(Spacer(1, 4))
        
        code_metrics = report_data.get('codeMetrics', {})
        
        languages_pct = code_metrics.get('languagesWithPct', {})
        if isinstance(languages_pct, dict) and languages_pct:
            lang_str = ', '.join([f"{lang}: {pct:.1f}%" for lang, pct in list(languages_pct.items())[:5]])
        else:
            lang_str = ', '.join(code_metrics.get('languages', [])) or 'Not detected'
        
        tech_stack = code_metrics.get('techStack', [])
        frameworks = code_metrics.get('frameworks', [])
        stack_str = ', '.join(set(tech_stack + frameworks)) if (tech_stack or frameworks) else 'Not detected'
        
        metrics_data = [
            ['Metric', 'Value'],
            ['Total Files', str(code_metrics.get('totalFiles', 0))],
            ['Lines of Code', f"{code_metrics.get('totalLinesOfCode', 0):,}"],
            ['Languages', lang_str],
            ['Frameworks', stack_str],
            ['Architecture', code_metrics.get('architecturePattern', 'Unknown')],
        ]
        
        metrics_table = Table(metrics_data, colWidths=[1.5*inch, 3.7*inch])
        metrics_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(self.SLATE_50)),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor(self.SLATE_700)),
            ('TEXTCOLOR', (0, 1), (0, -1), colors.HexColor(self.SLATE_500)),
            ('TEXTCOLOR', (1, 1), (1, -1), colors.HexColor(self.SLATE_700)),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('LINEBELOW', (0, 0), (-1, -1), 0.3, colors.HexColor('#f1f5f9')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(metrics_table)
        
        # Maturity indicators
        maturity = report_data.get('maturity', {})
        if maturity:
            items = []
            if maturity.get('hasTests'): items.append(f"Tests ({maturity.get('testFiles', 0)} files)")
            else: items.append("No tests")
            if maturity.get('hasCI'): items.append("CI/CD")
            if maturity.get('hasDocker'): items.append("Docker")
            if maturity.get('hasReadme'): items.append("README")
            if items:
                story.append(Spacer(1, 4))
                story.append(Paragraph(f"<b>Engineering Maturity:</b> {' | '.join(items)}", self.styles['RPT_Body']))
        
        # ========== CONTRIBUTORS ==========
        story.append(SectionHeader("Contributors", "TEAM", '#6366f1'))
        story.append(Spacer(1, 6))
        
        commits_data = report_data.get('commits', {})
        total_commits = commits_data.get('total', 0)
        story.append(Paragraph(f"Total Commits: <b>{total_commits}</b>", self.styles['RPT_Body']))
        story.append(Spacer(1, 4))
        
        contributors = commits_data.get('contributors', [])
        story.append(self._create_contributors_table(contributors))

        weekly_marks = report_data.get('weeklyIndividualMarks', [])
        if weekly_marks:
            story.append(Spacer(1, 6))
            story.append(Paragraph(
                "<b>Weekly Individual Marks</b> (Based on contribution share for this week)",
                self.styles['RPT_Subsection']
            ))
            story.append(self._create_weekly_marks_table(weekly_marks))
        
        # ========== INDIVIDUAL STUDENT SCORES ==========
        individual_scores = report_data.get('individualStudentScores', [])
        if individual_scores:
            story.append(Spacer(1, 6))
            story.append(Paragraph(
                "<b>Individual Student Scores</b> (Based on contribution, effort, and code quality)",
                self.styles['RPT_Subsection']
            ))
            story.append(self._create_individual_scores_table(individual_scores))
        
        # ========== RECENT COMMITS ==========
        recent_commits = commits_data.get('recentCommits', [])
        if recent_commits:
            story.append(SectionHeader("Recent Commits", "COMMITS", self.SLATE_500))
            story.append(Spacer(1, 4))
            
            for i, commit in enumerate(recent_commits[:8]):
                message = str(commit.get('message', 'No message'))[:60]
                author = commit.get('author', 'Unknown')
                date = commit.get('date', '')
                sha = commit.get('sha', '')[:7] if commit.get('sha') else ''
                
                story.append(Paragraph(f"<b>{i+1}.</b> {message}", self.styles['RPT_CommitMsg']))
                story.append(Paragraph(f"   by {author} - {date} - {sha}", self.styles['RPT_CommitMeta']))
            
            story.append(Spacer(1, 8))

        # ========== COMMIT INTEGRITY & DEDUCTIONS ==========
        commit_quality = report_data.get('commitQuality', {})
        marks_deduction = report_data.get('marksDeduction', {})
        if commit_quality or marks_deduction:
            story.append(SectionHeader("Commit Integrity & Deductions", "INTEGRITY", self.ORANGE))
            story.append(Spacer(1, 4))

            fake_count = commit_quality.get('fakeCommits', 0)
            try:
                fake_pct = float(commit_quality.get('fakeCommitPercentage', 0) or 0)
            except (TypeError, ValueError):
                fake_pct = 0.0
            commit_health = html.escape(str(commit_quality.get('healthStatus', 'Unknown')))
            story.append(Paragraph(
                f"Fake Commits: <b>{fake_count}</b> ({fake_pct:.1f}%) | Commit Health: <b>{commit_health}</b>",
                self.styles['RPT_Body']
            ))

            critical_warning = commit_quality.get('criticalWarning', {}) or {}
            if isinstance(critical_warning, dict) and critical_warning.get('show'):
                warning_title = html.escape(str(critical_warning.get('title', 'Critical Repository Violation')))
                warning_message = html.escape(str(critical_warning.get('message', 'Automated commit authors detected.')))
                warning_action = html.escape(str(critical_warning.get('action', 'Meet mentor immediately')))
                story.append(Spacer(1, 3))
                story.append(Paragraph(
                    f"<font color='{self.RED}'><b>{warning_title.upper()} - AUTOMATION COMMITS NOT ACCEPTED</b></font>",
                    self.styles['RPT_Body']
                ))
                story.append(Paragraph(
                    f"<font color='{self.RED}'><b>{warning_message}</b></font>",
                    self.styles['RPT_Con']
                ))
                story.append(Paragraph(
                    f"<font color='{self.RED}'><b>Action Required: {warning_action}</b></font>",
                    self.styles['RPT_Con']
                ))

                ai_bot_contributors = commit_quality.get('aiBotContributors', []) or []
                if isinstance(ai_bot_contributors, list) and ai_bot_contributors:
                    story.append(Paragraph("<b>Automated Contributor Accounts:</b>", self.styles['RPT_Subsection']))
                    for bot in ai_bot_contributors[:6]:
                        if not isinstance(bot, dict):
                            continue
                        bot_name = html.escape(str(bot.get('name', 'Unknown')))
                        bot_tool = html.escape(str(bot.get('tool', 'BOT')))
                        bot_commits = bot.get('commits', 0)
                        bot_share = bot.get('share', 0)
                        story.append(Paragraph(
                            f"<font color='{self.RED}'><b>{bot_name.upper()} - AUTOMATION COMMIT (NOT ACCEPTED)</b></font> "
                            f"({bot_commits} commits, {bot_share}%, {bot_tool})",
                            self.styles['RPT_Con']
                        ))

            ai_tools = commit_quality.get('aiToolsDetected', [])
            if ai_tools:
                safe_ai_tools = [html.escape(str(t)) for t in ai_tools[:10]]
                story.append(Paragraph(
                    f"AI Tools Detected in Commit History: <b>{', '.join(safe_ai_tools)}</b>",
                    self.styles['RPT_Body']
                ))
            else:
                story.append(Paragraph(
                    "AI Tools Detected in Commit History: <b>None</b>",
                    self.styles['RPT_Body']
                ))

            if fake_count > 0:
                example_fake_commits = commit_quality.get('exampleFakeCommits', [])
                if example_fake_commits:
                    story.append(Paragraph("<b>Example Flagged Commits:</b>", self.styles['RPT_Subsection']))
                    for i, commit in enumerate(example_fake_commits[:5], 1):
                        sha = html.escape(str(commit.get('sha', '')))
                        message = html.escape(str(commit.get('message', 'No message')))
                        reasons = commit.get('reasons', [])
                        reason_text_raw = ', '.join(reasons[:3]) if isinstance(reasons, list) else str(reasons)
                        reason_text = html.escape(reason_text_raw)
                        story.append(Paragraph(
                            f"{i}. {sha} - {message}",
                            self.styles['RPT_CommitMsg']
                        ))
                        if reason_text:
                            story.append(Paragraph(
                                f"   Reason: {reason_text}",
                                self.styles['RPT_CommitMeta']
                            ))

            deduction_applied = marks_deduction.get('applied', False)
            if deduction_applied:
                try:
                    deducted_pct = float(marks_deduction.get('marksDeductedPercentage', 0) or 0)
                except (TypeError, ValueError):
                    deducted_pct = 0.0
                reason = html.escape(str(marks_deduction.get('reason', '')))
                story.append(Spacer(1, 4))
                story.append(Paragraph(
                    f"<font color='{self.RED}'><b>Marks Deducted:</b> {deducted_pct:.1f}%</font>",
                    self.styles['RPT_Body']
                ))
                if reason:
                    story.append(Paragraph(f"<b>Deduction Reason:</b> {reason}", self.styles['RPT_Con']))
            else:
                story.append(Paragraph("<b>Marks Deducted:</b> 0%", self.styles['RPT_Body']))

            story.append(Spacer(1, 8))
        
        # ========== AI ANALYSIS ==========
        story.append(SectionHeader("AI Analysis & Feedback", "AI", '#8b5cf6'))
        story.append(Spacer(1, 6))
        
        ai_analysis = report_data.get('aiAnalysis', {})
        ai_pct = ai_analysis.get('aiGeneratedPercentage', 0)
        verdict = ai_analysis.get('verdict', 'Unknown')
        
        ai_color = self.RED if ai_pct > 50 else self.AMBER if ai_pct > 25 else self.GREEN
        story.append(Paragraph(
            f"AI-Generated Content: <font color='{ai_color}'><b>{ai_pct:.1f}%</b></font> | Verdict: <b>{verdict}</b>",
            self.styles['RPT_Body']
        ))
        
        # Features
        features = ai_analysis.get('features', [])
        if features:
            story.append(Paragraph("<b>Features Implemented:</b>", self.styles['RPT_Subsection']))
            for feat in features[:6]:
                story.append(Paragraph(f"- {feat}", self.styles['RPT_Feature']))
        
        # Positive Feedback
        positive = ai_analysis.get('positiveFeedback', '')
        strengths = ai_analysis.get('strengths', [])
        if positive:
            story.append(Paragraph("<b>Positive Feedback:</b>", self.styles['RPT_Subsection']))
            story.append(Paragraph(positive, self.styles['RPT_Pro']))
        elif strengths:
            story.append(Paragraph("<b>Strengths:</b>", self.styles['RPT_Subsection']))
            for s in (strengths[:5] if isinstance(strengths, list) else [strengths]):
                if s and len(str(s)) > 2:
                    story.append(Paragraph(f"- {s}", self.styles['RPT_Pro']))
        
        # Constructive Feedback
        constructive = ai_analysis.get('constructiveFeedback', '')
        improvements = ai_analysis.get('improvements', [])
        if constructive:
            story.append(Paragraph("<b>Areas for Improvement:</b>", self.styles['RPT_Subsection']))
            story.append(Paragraph(constructive, self.styles['RPT_Con']))
        elif improvements:
            story.append(Paragraph("<b>Areas for Improvement:</b>", self.styles['RPT_Subsection']))
            for imp in (improvements[:5] if isinstance(improvements, list) else [improvements]):
                if imp and len(str(imp)) > 2:
                    story.append(Paragraph(f"- {imp}", self.styles['RPT_Con']))
        
        # ========== FEATURE ANALYSIS ==========
        feature_analysis = ai_analysis.get('featureAnalysis', [])
        if feature_analysis:
            story.append(SectionHeader("Feature-by-Feature Analysis", "FEATURES", self.BLUE))
            story.append(Spacer(1, 4))
            
            for feat in feature_analysis[:6]:
                if isinstance(feat, dict):
                    feat_name = feat.get('feature_name', 'Unknown Feature')
                    status = feat.get('status', 'Unknown')
                    quality = feat.get('implementation_quality', 'N/A')
                    
                    status_color = self.GREEN if status == 'Implemented' else self.AMBER if status == 'Partial' else self.RED
                    
                    story.append(Paragraph(
                        f"<b>{feat_name}</b> - <font color='{status_color}'>{status}</font> | Quality: {quality}",
                        self.styles['RPT_Subsection']
                    ))
                    
                    working = feat.get('whats_working', '')
                    if working:
                        story.append(Paragraph(f"Good: {working}", self.styles['RPT_Pro']))
                    
                    needs_improvement = feat.get('improvements_needed', '')
                    if needs_improvement:
                        story.append(Paragraph(f"Needs improvement: {needs_improvement}", self.styles['RPT_Con']))
                    
                    story.append(Spacer(1, 4))
        
        # ========== PRODUCT ANALYSIS ==========
        product_analysis = report_data.get('productAnalysis', {})
        if product_analysis and any(product_analysis.values()):
            story.append(SectionHeader("Product Analysis", "PRODUCT", '#0891b2'))
            story.append(Spacer(1, 4))
            
            for key, label in [
                ('core_value_proposition', 'Value Proposition'),
                ('target_users', 'Target Users'),
                ('competitive_advantage', 'Competitive Advantage'),
            ]:
                val = product_analysis.get(key, '')
                if val:
                    story.append(Paragraph(f"<b>{label}:</b> {val}", self.styles['RPT_Body']))
            
            readiness = product_analysis.get('market_readiness', '')
            if readiness:
                rc = self.GREEN if readiness == 'Ready' else self.AMBER if readiness == 'Needs Polish' else self.RED
                story.append(Paragraph(
                    f"<b>Market Readiness:</b> <font color='{rc}'><b>{readiness}</b></font>",
                    self.styles['RPT_Body']
                ))
        
        # ========== SUGGESTED FEATURES ==========
        suggested = ai_analysis.get('suggestedFeatures', [])
        if suggested:
            story.append(SectionHeader("Suggested New Features", "IDEAS", self.AMBER))
            story.append(Spacer(1, 4))
            
            for i, s in enumerate(suggested[:5], 1):
                if isinstance(s, dict):
                    name = s.get('feature_name', 'Unknown')
                    priority = s.get('priority', 'Medium')
                    reason = s.get('reason', '')
                    hint = s.get('implementation_hint', '')
                    
                    pc = self.RED if priority == 'High' else self.AMBER if priority == 'Medium' else self.SLATE_500
                    
                    story.append(Paragraph(
                        f"<b>{i}. {name}</b> - <font color='{pc}'>Priority: {priority}</font>",
                        self.styles['RPT_Subsection']
                    ))
                    if reason:
                        story.append(Paragraph(f"   Why: {reason}", self.styles['RPT_Body']))
                    if hint:
                        story.append(Paragraph(f"   How: {hint}", self.styles['RPT_Feature']))
        
        # ========== OVERALL RECOMMENDATION ==========
        recommendation = ai_analysis.get('overallRecommendation', '')
        if recommendation:
            story.append(SectionHeader("Overall Recommendation", "SUMMARY", self.NAVY))
            story.append(Spacer(1, 4))
            story.append(Paragraph(recommendation, self.styles['RPT_Body']))

        # ========== SECURITY SECTION ==========
        story.append(SectionHeader("Security Analysis", "SECURITY", self.RED))
        story.append(Spacer(1, 6))
        
        security = report_data.get('security', {})
        security_score = self._to_float(security.get('score', 0), 0.0)
        secrets_score = self._to_float(security.get('secretsScore'), None)
        practices_score = self._to_float(security.get('practicesScore'), None)
        secrets_detected = int(self._to_float(security.get('secretsDetected', 0), 0.0))
        
        sec_color = self._get_score_color(security_score)
        if secrets_score is not None and practices_score is not None:
            story.append(Paragraph(
                f"Security Score: <font color='{sec_color}'><b>{security_score:.1f}/100</b></font> "
                f"(Secrets: {secrets_score:.1f}, Practices: {practices_score:.1f}) | "
                f"Secrets Detected: <b>{secrets_detected}</b>",
                self.styles['RPT_Body']
            ))
        else:
            story.append(Paragraph(
                f"Security Score: <font color='{sec_color}'><b>{security_score:.1f}/100</b></font> | "
                f"Secrets Detected: <b>{secrets_detected}</b>",
                self.styles['RPT_Body']
            ))
        
        # Detected leaks
        leaks = security.get('leaks', [])
        if leaks:
            story.append(Spacer(1, 8))
            story.append(Paragraph("<b>Detected Secrets:</b>", self.styles['RPT_Subsection']))
            
            for i, leak in enumerate(leaks[:10], 1):
                leak_type = leak.get('type', 'Unknown')
                file_path = leak.get('path', 'Unknown file')
                line_num = leak.get('line_number', '?')
                severity = leak.get('severity', 'medium')
                confidence = leak.get('confidence', 0.5)
                
                sev_color = {'high': self.RED, 'medium': self.AMBER, 'low': self.GREEN}.get(severity, self.SLATE_500)
                
                story.append(Paragraph(
                    f"<b>{i}. {leak_type}</b> <font color='{sev_color}'>[{severity.upper()}]</font>",
                    self.styles['RPT_Body']
                ))
                story.append(Paragraph(
                    f"   File: {file_path} (Line {line_num}) | Confidence: {confidence:.0%}",
                    self.styles['RPT_Small']
                ))
            
            if len(leaks) > 10:
                story.append(Paragraph(
                    f"... and {len(leaks) - 10} more secrets detected",
                    self.styles['RPT_Small']
                ))
        
        # Best practices
        best_practices = security.get('bestPractices', [])
        if best_practices:
            story.append(Spacer(1, 8))
            story.append(Paragraph("<b>Security Best Practices:</b>", self.styles['RPT_Subsection']))
            
            for practice in best_practices:
                name = practice.get('practice_name', 'Unknown')
                status = practice.get('status', 'not_implemented')
                
                icon = "OK" if status == "implemented" else "NO"
                ic = self.GREEN if status == "implemented" else self.RED
                
                story.append(Paragraph(
                    f"<font color='{ic}'>{icon}</font> {name}",
                    self.styles['RPT_Body']
                ))
        
        # Recommendations
        recommendations = security.get('recommendations', [])
        if recommendations:
            story.append(Spacer(1, 8))
            story.append(Paragraph("<b>Security Recommendations:</b>", self.styles['RPT_Subsection']))
            
            for i, rec in enumerate(recommendations[:5], 1):
                title = rec.get('title', 'Recommendation')
                description = rec.get('description', '')
                priority = rec.get('priority', 5)
                
                pc = self.RED if priority >= 8 else self.AMBER if priority >= 5 else self.GREEN
                
                story.append(Paragraph(
                    f"<b>{i}. {title}</b> <font color='{pc}'>[Priority: {priority}/10]</font>",
                    self.styles['RPT_Body']
                ))
                if description:
                    story.append(Paragraph(f"   {description}", self.styles['RPT_Small']))
            
            if len(recommendations) > 5:
                story.append(Paragraph(f"... and {len(recommendations) - 5} more", self.styles['RPT_Small']))
        
        # Legacy security issues
        security_issues = security.get('issues', [])
        if security_issues and not leaks:
            story.append(Paragraph("<b>Security Issues:</b>", self.styles['RPT_Subsection']))
            story.append(self._create_security_issues_table(security_issues))
        elif not leaks and not security_issues:
            story.append(Paragraph("No security issues detected.", self.styles['RPT_Body']))
        
        # ========== RISKY FILES ==========
        risky_files = report_data.get('riskyFiles', [])
        if risky_files:
            story.append(SectionHeader("Files Requiring Review", "RISK", self.ORANGE))
            story.append(Spacer(1, 4))
            story.append(Paragraph("Files flagged for potential AI generation or similarity issues:", self.styles['RPT_Body']))
            story.append(self._create_risky_files_table(risky_files))
        
        # ========== RISK FLAGS ==========
        risk_flags = report_data.get('riskFlags', [])
        if risk_flags:
            story.append(SectionHeader("Risk Flags", "FLAGS", self.RED))
            story.append(Spacer(1, 4))
            for flag in risk_flags:
                story.append(Paragraph(f"- {flag}", self.styles['RPT_Con']))
        
        # ========== FOOTER ==========
        story.append(Spacer(1, 25))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor(self.SLATE_200)))
        story.append(Spacer(1, 6))
        
        last_analyzed = report_data.get('lastAnalyzedAt', '')
        if last_analyzed:
            try:
                analyzed_date = datetime.fromisoformat(last_analyzed.replace('Z', '+00:00'))
                ist_analyzed = analyzed_date + timedelta(hours=5, minutes=30)
                analyzed_str = ist_analyzed.strftime('%B %d, %Y - %I:%M %p IST')
                story.append(Paragraph(f"Last Analysis: {analyzed_str}", self.styles['RPT_Footer']))
            except:
                pass
        
        story.append(Paragraph(
            "Generated by <b>ProjectFlow</b> - GitHub Analysis System",
            self.styles['RPT_Footer']
        ))
        
        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes


def generate_team_report_pdf(report_data: Dict[str, Any]) -> bytes:
    """
    Generate a PDF report for a team.
    
    Args:
        report_data: Dictionary containing team report data
        
    Returns:
        PDF file as bytes
    """
    generator = TeamReportPDFGenerator()
    return generator.generate(report_data)
