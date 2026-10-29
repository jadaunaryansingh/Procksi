import matplotlib
# Use the 'Agg' backend to prevent Tkinter error/crash in threaded environments
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import os
from datetime import datetime

def generate_dashboard(metrics: dict, file_data: list, output_path: str = "hackathon_report.png") -> str:
    """
    Generates a comprehensive 2-panel dashboard:
    1. Radar Chart: Overall Project Health
    2. Scatter Plot: File-wise Risk Analysis (Algorithmic vs LLM)
    """
    # Validate output_path
    if not output_path or output_path == "N/A":
        output_path = "hackathon_report.png"
    
    # Create figure with 2 subplots
    fig = plt.figure(figsize=(14, 7))
    plt.suptitle(f"Hackathon Forensic Audit Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}", fontsize=16, weight='bold')

    # ==========================================
    # Plot 1: Radar Chart (Overall Metrics)
    # ==========================================
    ax1 = fig.add_subplot(121, polar=True)
    
    # Data Setup
    labels = ['Originality\n(Non-AI)', 'Code Quality\n(Maintainability)', 'Team Effort\n(Activity)', 'Documentation\n(Comments)']
    values = [
        float(metrics.get("originality", 0)),
        float(metrics.get("maintainability", 0)),
        float(metrics.get("effort", 0)),
        float(metrics.get("documentation", 0))
    ]
    
    # Close the loop
    values += values[:1]
    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
    angles += angles[:1]

    # Draw
    ax1.set_theta_offset(np.pi / 2)
    ax1.set_theta_direction(-1)
    ax1.set_xticks(angles[:-1])
    ax1.set_xticklabels(labels, size=10)
    ax1.set_ylim(0, 100)
    
    ax1.plot(angles, values, linewidth=2, linestyle='solid', color='#1f77b4', label="Project Score")
    ax1.fill(angles, values, '#1f77b4', alpha=0.25)
    ax1.legend(loc='upper right', bbox_to_anchor=(0.1, 0.1))
    ax1.set_title("Overall Project Health", y=1.08, size=12, weight='bold')

    # ==========================================
    # Plot 2: Scatter Plot (File Risk Analysis)
    # ==========================================
    ax2 = fig.add_subplot(122)
    
    if file_data:
        # Extract data
        filenames = [os.path.basename(f['path']) for f in file_data]
        alg_scores = [f['S_alg'] * 100 for f in file_data] # Convert to %
        llm_scores = [f['S_llm'] * 100 for f in file_data] # Convert to %
        sizes = [f['S_cross'] * 300 + 50 for f in file_data] # Bubble size based on risk
        
        # Color mapping (Red=High Risk, Green=Safe)
        colors = ['red' if s > 50 else 'orange' if s > 20 else 'green' for s in alg_scores]

        scatter = ax2.scatter(llm_scores, alg_scores, s=sizes, c=colors, alpha=0.6, edgecolors="w", linewidth=2)
        
        # Labels and Zones
        ax2.set_xlabel("AI / LLM Probability (%)", fontsize=10)
        ax2.set_ylabel("Internal Similarity / Plagiarism (%)", fontsize=10)
        ax2.set_xlim(-5, 105)
        ax2.set_ylim(-5, 105)
        ax2.grid(True, linestyle='--', alpha=0.5)
        
        # Add risk thresholds
        ax2.axhline(y=30, color='gray', linestyle=':', alpha=0.5)
        ax2.axvline(x=30, color='gray', linestyle=':', alpha=0.5)
        ax2.text(95, 95, "CRITICAL RISK", color='red', ha='right', va='top', weight='bold')
        ax2.text(5, 5, "SAFE ZONE", color='green', ha='left', va='bottom', weight='bold')
        
        # Annotate top 3 risky files
        # Sort by cross score
        sorted_files = sorted(file_data, key=lambda x: x['S_cross'], reverse=True)[:3]
        for f in sorted_files:
            x = f['S_llm'] * 100
            y = f['S_alg'] * 100
            name = os.path.basename(f['path'])
            ax2.annotate(name, (x, y), xytext=(x+2, y+2), fontsize=8, arrowprops=dict(arrowstyle="->", color='black'))
            
        ax2.set_title("File-wise Risk Distribution", size=12, weight='bold')
    else:
        ax2.text(0.5, 0.5, "No File Data Available", ha='center', va='center')

    # Save
    if os.path.dirname(output_path):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    
    return output_path