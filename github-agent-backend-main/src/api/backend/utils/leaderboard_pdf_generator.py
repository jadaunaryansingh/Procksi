"""
Leaderboard PDF Generator
Generates modern, visually polished PDF reports for batch leaderboards
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, Flowable
)
from reportlab.graphics.shapes import Drawing, Rect, String, Circle
from reportlab.graphics import renderPDF
from io import BytesIO
from datetime import datetime, timedelta
from typing import Dict, Any, List


# ======================== CUSTOM FLOWABLES ========================

class HeaderBand(Flowable):
    """Full-width navy header band with title and subtitle."""
    
    def __init__(self, title: str, subtitle: str, date_str: str, width: float = None):
        Flowable.__init__(self)
        self.title = title
        self.subtitle = subtitle
        self.date_str = date_str
        self._width = width or (A4[0] - 80)  # page width minus margins
        self.height = 75
    
    def wrap(self, availWidth, availHeight):
        self._width = availWidth
        return (self._width, self.height)
    
    def draw(self):
        c = self.canv
        w, h = self._width, self.height
        
        # Navy background
        c.setFillColor(colors.HexColor('#0f172a'))
        c.roundRect(0, 0, w, h, 8, fill=1, stroke=0)
        
        # Accent stripe at bottom
        c.setFillColor(colors.HexColor('#2563eb'))
        c.rect(0, 0, w, 4, fill=1, stroke=0)
        
        # Title
        c.setFillColor(colors.white)
        c.setFont('Helvetica-Bold', 22)
        c.drawCentredString(w / 2, h - 30, self.title)
        
        # Subtitle (batch name)
        c.setFont('Helvetica', 12)
        c.setFillColor(colors.HexColor('#93c5fd'))
        c.drawCentredString(w / 2, h - 48, self.subtitle)
        
        # Date
        c.setFont('Helvetica', 9)
        c.setFillColor(colors.HexColor('#64748b'))
        c.drawCentredString(w / 2, 14, self.date_str)


class StatsRow(Flowable):
    """Row of stat cards with colored accents."""
    
    def __init__(self, stats: List[Dict[str, Any]], width: float = None):
        Flowable.__init__(self)
        self.stats = stats  # [{"label": str, "value": str, "color": str}]
        self._width = width or (A4[0] - 80)
        self.height = 50
    
    def wrap(self, availWidth, availHeight):
        self._width = availWidth
        return (self._width, self.height)
    
    def draw(self):
        c = self.canv
        n = len(self.stats)
        if n == 0:
            return
        
        gap = 12
        card_w = (self._width - gap * (n - 1)) / n
        
        for i, stat in enumerate(self.stats):
            x = i * (card_w + gap)
            accent = colors.HexColor(stat.get('color', '#2563eb'))
            
            # Card background
            c.setStrokeColor(colors.HexColor('#e2e8f0'))
            c.setFillColor(colors.HexColor('#f8fafc'))
            c.roundRect(x, 0, card_w, self.height, 6, fill=1, stroke=1)
            
            # Accent top bar
            c.setFillColor(accent)
            c.rect(x + 8, self.height - 6, card_w - 16, 3, fill=1, stroke=0)
            
            # Value
            c.setFillColor(colors.HexColor('#0f172a'))
            c.setFont('Helvetica-Bold', 20)
            c.drawCentredString(x + card_w / 2, 22, str(stat.get('value', '')))
            
            # Label
            c.setFillColor(colors.HexColor('#64748b'))
            c.setFont('Helvetica', 9)
            c.drawCentredString(x + card_w / 2, 8, stat.get('label', ''))


class ScoreBadge(Flowable):
    """Small colored circular badge for scores."""
    
    def __init__(self, score: float, size: int = 28):
        Flowable.__init__(self)
        self.score = score
        self.size = size
        self.width = size
        self.height = size
    
    def wrap(self, availWidth, availHeight):
        return (self.size, self.size)
    
    def draw(self):
        c = self.canv
        r = self.size / 2
        
        if self.score >= 80:
            bg = '#dcfce7'
            fg = '#16a34a'
        elif self.score >= 60:
            bg = '#fef9c3'
            fg = '#ca8a04'
        elif self.score >= 40:
            bg = '#ffedd5'
            fg = '#ea580c'
        else:
            bg = '#fee2e2'
            fg = '#dc2626'
        
        c.setFillColor(colors.HexColor(bg))
        c.circle(r, r, r, fill=1, stroke=0)
        
        c.setFillColor(colors.HexColor(fg))
        c.setFont('Helvetica-Bold', 9)
        c.drawCentredString(r, r - 3, f"{self.score:.0f}")


# ======================== MAIN GENERATOR ========================

class LeaderboardPDFGenerator:
    """Generates modern PDF reports for batch leaderboards."""
    
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
    GOLD = '#eab308'
    SILVER = '#94a3b8'
    BRONZE = '#b45309'
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        self.styles.add(ParagraphStyle(
            name='LB_SectionTitle',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceBefore=18,
            spaceAfter=10,
            textColor=colors.HexColor(self.NAVY),
            fontName='Helvetica-Bold'
        ))
        self.styles.add(ParagraphStyle(
            name='LB_Body',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=6,
            textColor=colors.HexColor(self.SLATE_700)
        ))
        self.styles.add(ParagraphStyle(
            name='LB_Footer',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor(self.SLATE_500),
            alignment=1
        ))
    
    def _get_score_color(self, score: float) -> str:
        if score >= 80: return self.GREEN
        elif score >= 60: return self.AMBER
        elif score >= 40: return self.ORANGE
        else: return self.RED
    
    def _get_rank_display(self, rank: int) -> str:
        if rank == 1: return "🥇"
        elif rank == 2: return "🥈"
        elif rank == 3: return "🥉"
        else:
            if 11 <= rank <= 13:
                return f"{rank}th"
            last = rank % 10
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(last, 'th')
            return f"{rank}{suffix}"
    
    def _create_leaderboard_table(self, entries: List[Dict[str, Any]], recipient_team_id: str = None) -> Table:
        """Create a modern styled leaderboard table."""
        
        # Header row
        data = [['  #', 'Team Name', 'Project', 'CI/CD', 'Score']]
        
        for entry in entries:
            rank = entry.get('rank', 0)
            t_name = entry.get('team_name') or 'Unknown'
            team_name = str(t_name)[:28]
            p_name = entry.get('project_name')
            project = str(p_name)[:32] if p_name else '—'
            score = entry.get('overall_score') or 0
            team_id = entry.get('team_id', '')
            
            # CI/CD label
            ci_cd_label = "—"
            report_json = entry.get('report_json')
            if isinstance(report_json, dict):
                maturity = report_json.get('maturity', {})
                if isinstance(maturity, dict):
                    ci_cd = maturity.get('ci_cd')
                    if isinstance(ci_cd, dict) and ci_cd.get('has_ci_cd'):
                        run_history = ci_cd.get('run_history')
                        if run_history and run_history.get('total_runs', 0) > 0:
                            ci_cd_label = f"{run_history.get('pass_rate', 0)}%"
                        else:
                            ci_cd_label = "✓"
            
            rank_str = self._get_rank_display(rank)
            
            # Highlight recipient
            if recipient_team_id and team_id == recipient_team_id:
                team_name = f"► {team_name}"
            
            score_color = self._get_score_color(score)
            score_cell = Paragraph(
                f"<font color='{score_color}'><b>{score:.1f}</b></font>",
                ParagraphStyle(name='ScoreCell', fontSize=10, alignment=1, fontName='Helvetica-Bold')
            )
            
            data.append([rank_str, team_name, project, ci_cd_label, score_cell])
        
        if not entries:
            data.append(['—', 'No teams available', '—', '—', '—'])
        
        table = Table(data, colWidths=[0.55*inch, 1.9*inch, 2*inch, 0.6*inch, 0.7*inch], repeatRows=1)
        
        style = TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(self.NAVY)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('TOPPADDING', (0, 0), (-1, 0), 6),
            
            # Body
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            
            # Subtle grid
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor('#f1f5f9')),
            ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.HexColor(self.BLUE)),
            
            # Alignment
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (3, 0), (3, -1), 'CENTER'),
            ('ALIGN', (4, 0), (4, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Alternating rows
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(self.SLATE_50)]),
        ])
        
        # Highlight top 3 rank cells
        rank_styles = [
            (1, self.GOLD, '#fefce8'),
            (2, self.SILVER, '#f8fafc'),
            (3, self.BRONZE, '#fffbeb'),
        ]
        for row, text_color, bg_color in rank_styles:
            if row < len(data):
                style.add('TEXTCOLOR', (0, row), (0, row), colors.HexColor(text_color))
                style.add('FONTNAME', (0, row), (0, row), 'Helvetica-Bold')
                style.add('FONTSIZE', (0, row), (0, row), 12)
        
        # Highlight recipient row
        if recipient_team_id:
            for i, entry in enumerate(entries, 1):
                if entry.get('team_id') == recipient_team_id:
                    style.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#dbeafe'))
                    style.add('FONTNAME', (0, i), (1, i), 'Helvetica-Bold')
                    break
        
        table.setStyle(style)
        return table
    
    def generate(self, leaderboard_data: Dict[str, Any], recipient_team_id: str = None) -> bytes:
        """Generate leaderboard PDF and return as bytes."""
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
        batch_name = leaderboard_data.get('batch_name', 'Unknown Batch')
        generated_at = leaderboard_data.get('generated_at', datetime.utcnow().isoformat())
        try:
            gen_date = datetime.fromisoformat(generated_at.replace('Z', '+00:00'))
            ist_date = gen_date + timedelta(hours=5, minutes=30)
            formatted_date = ist_date.strftime('%B %d, %Y • %I:%M %p IST')
        except:
            formatted_date = generated_at
        
        story.append(HeaderBand(
            title="BATCH LEADERBOARD",
            subtitle=batch_name,
            date_str=f"Generated: {formatted_date}"
        ))
        story.append(Spacer(1, 10))
        
        # ========== STATS ROW ==========
        entries = leaderboard_data.get('entries', [])
        total_teams = leaderboard_data.get('total_teams', len(entries))
        
        if entries:
            scores = [(e.get('overall_score') or 0) for e in entries]
            highest = max(scores) if scores else 0
            avg = sum(scores) / len(scores) if scores else 0
            
            story.append(StatsRow([
                {"label": "Highest Score", "value": f"{highest:.1f}", "color": self.GREEN},
                {"label": "Average Score", "value": f"{avg:.1f}", "color": self.BLUE},
                {"label": "Total Teams", "value": str(total_teams), "color": "#8b5cf6"},
            ]))
            story.append(Spacer(1, 12))
        
        # ========== LEADERBOARD TABLE ==========
        if entries:
            story.append(self._create_leaderboard_table(entries, recipient_team_id))
            story.append(Spacer(1, 12))
        else:
            story.append(Paragraph("No teams with scores available.", self.styles['LB_Body']))
        
        # ========== SCORE DISTRIBUTION ==========
        if entries:
            story.append(Spacer(1, 6))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor(self.SLATE_200)))
            story.append(Spacer(1, 8))
            story.append(Paragraph("📊 Score Distribution", self.styles['LB_SectionTitle']))
            
            scores = [(e.get('overall_score') or 0) for e in entries]
            excellent = len([s for s in scores if s >= 80])
            good = len([s for s in scores if 60 <= s < 80])
            fair = len([s for s in scores if 40 <= s < 60])
            needs_work = len([s for s in scores if s < 40])
            total = len(scores)
            
            dist_data = [
                ['Category', 'Count', '%'],
                [Paragraph(f"<font color='{self.GREEN}'>●</font> Excellent (80–100)", self.styles['LB_Body']),
                 str(excellent), f"{excellent/total*100:.0f}%"],
                [Paragraph(f"<font color='{self.AMBER}'>●</font> Good (60–79)", self.styles['LB_Body']),
                 str(good), f"{good/total*100:.0f}%"],
                [Paragraph(f"<font color='{self.ORANGE}'>●</font> Fair (40–59)", self.styles['LB_Body']),
                 str(fair), f"{fair/total*100:.0f}%"],
                [Paragraph(f"<font color='{self.RED}'>●</font> Needs Work (0–39)", self.styles['LB_Body']),
                 str(needs_work), f"{needs_work/total*100:.0f}%"],
            ]
            
            dist_table = Table(dist_data, colWidths=[3*inch, 0.8*inch, 0.8*inch])
            dist_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(self.SLATE_50)),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor(self.SLATE_700)),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
                ('LINEBELOW', (0, 0), (-1, -1), 0.3, colors.HexColor('#f1f5f9')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(dist_table)
        
        # ========== FOOTER ==========
        story.append(Spacer(1, 15))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor(self.SLATE_200)))
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            "Generated by <b>ProjectFlow</b> — GitHub Analysis System",
            self.styles['LB_Footer']
        ))
        story.append(Paragraph(
            "Rankings based on quality, security, originality, architecture & documentation scores.",
            ParagraphStyle(name='LB_Footnote', fontSize=7, textColor=colors.HexColor(self.SLATE_500), alignment=1)
        ))
        
        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes


def generate_leaderboard_pdf(leaderboard_data: Dict[str, Any], recipient_team_id: str = None) -> bytes:
    """
    Generate a leaderboard PDF report.
    
    Args:
        leaderboard_data: Dictionary containing leaderboard data
        recipient_team_id: Optional team ID to highlight
        
    Returns:
        PDF file as bytes
    """
    generator = LeaderboardPDFGenerator()
    return generator.generate(leaderboard_data, recipient_team_id)
