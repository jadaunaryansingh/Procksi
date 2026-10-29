import json
import os
from typing import Dict, Any
from datetime import datetime
from pathlib import Path

def write_json_report(report_obj: Dict[str, Any], path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report_obj, f, indent=2)

def generate_simple_html(report_obj: Dict[str, Any], outdir: str):
    os.makedirs(outdir, exist_ok=True)
    # Create a minimal HTML summarizing key findings
    html = "<html><head><meta charset='utf-8'><title>Repo Audit Report</title></head><body>"
    html += f"<h1>Repo Audit Report — {report_obj.get('repo')}</h1>"
    html += f"<p>Generated: {datetime.utcnow().isoformat()}Z</p>"
    html += "<h2>Executive summary</h2>"
    html += f"<p>Plagiarism (top): {report_obj.get('overall',{}).get('top_plag_percent', 0):.1f}%</p>"
    html += f"<p>LLM-origin (top): {report_obj.get('overall',{}).get('top_llm_percent', 0):.1f}%</p>"
    html += "<h2>Top flagged files</h2><ul>"
    for f in report_obj.get("files", [])[:20]:
        html += f"<li>{f['path']} — plag={f['P_alg_percent']:.1f} llm={f['P_llm_percent']:.1f} risk={f['R_llm_plag_percent']:.1f}</li>"
    html += "</ul>"
    html += "</body></html>"
    Path(outdir, "report.html").write_text(html, encoding="utf-8")
