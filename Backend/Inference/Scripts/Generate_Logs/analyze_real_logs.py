"""
WalkSense - Real Log Data Analysis
Generates evaluation graphs from ACTUAL performance logs for grounding proof
"""

import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import pandas as pd
from pathlib import Path
import json
import re
from datetime import datetime

# Set style
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (12, 8)

# Paths
log_file = Path("logs/performance.log")
output_dir = Path("plots/real_data_analysis")
output_dir.mkdir(parents=True, exist_ok=True)

print("\n" + "="*70)
print("  WalkSense - Real Log Data Analysis")
print("="*70 + "\n")

# ============================================================================
# Parse Performance Logs
# ============================================================================
def parse_performance_log():
    """Extract performance metrics from actual log file"""
    
    if not log_file.exists():
        print(f"⚠️  Log file not found: {log_file}")
        return None
    
    print(f"📂 Reading log file: {log_file}")
    print(f"   Size: {log_file.stat().st_size / 1024:.2f} KB\n")
    
    metrics = {
        'yolo_times': [],
        'vlm_times': [],
        'stt_times': [],
        'llm_times': [],
        'frame_times': [],
        'timestamps': [],
        'detections': [],
        'alerts': []
    }
    
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                # Extract YOLO detection times
                if 'YOLO' in line and 'ms' in line:
                    match = re.search(r'(\d+\.?\d*)\s*ms', line)
                    if match:
                        metrics['yolo_times'].append(float(match.group(1)))
                
                # Extract VLM times
                if 'VLM' in line and ('took' in line or 'duration' in line):
                    match = re.search(r'(\d+\.?\d*)\s*s', line)
                    if match:
                        metrics['vlm_times'].append(float(match.group(1)) * 1000)
                
                # Extract STT times
                if 'STT' in line and 'Transcribing' in line:
                    match = re.search(r'(\d+\.?\d*)\s*ms', line)
                    if match:
                        metrics['stt_times'].append(float(match.group(1)))
                
                # Extract LLM times
                if 'LLM' in line and 'answer' in line.lower():
                    match = re.search(r'(\d+\.?\d*)\s*ms', line)
                    if match:
                        metrics['llm_times'].append(float(match.group(1)))
                
                # Extract frame processing times
                if 'Frame' in line and 'processed' in line:
                    match = re.search(r'(\d+\.?\d*)\s*ms', line)
                    if match:
                        metrics['frame_times'].append(float(match.group(1)))
                
                # Extract detection counts
                if 'detected' in line.lower():
                    match = re.search(r'(\d+)\s+objects?', line)
                    if match:
                        metrics['detections'].append(int(match.group(1)))
                
                # Extract alerts
                if any(word in line for word in ['CRITICAL', 'WARNING', 'INFO']):
                    if 'CRITICAL' in line:
                        metrics['alerts'].append('CRITICAL')
                    elif 'WARNING' in line:
                        metrics['alerts'].append('WARNING')
                    else:
                        metrics['alerts'].append('INFO')
                
            except Exception as e:
                continue
    
    # Print summary
    print("📊 Extracted Metrics:")
    print(f"   YOLO detections: {len(metrics['yolo_times'])} samples")
    print(f"   VLM inferences: {len(metrics['vlm_times'])} samples")
    print(f"   STT transcriptions: {len(metrics['stt_times'])} samples")
    print(f"   LLM responses: {len(metrics['llm_times'])} samples")
    print(f"   Total alerts: {len(metrics['alerts'])} events\n")
    
    return metrics


# ============================================================================
# GRAPH 1: Real YOLO Performance Distribution
# ============================================================================
def plot_real_yolo_performance(metrics):
    """Histogram of actual YOLO detection times from logs"""
    
    if not metrics['yolo_times']:
        print("⚠️  No YOLO data found in logs")
        return
    
    times = np.array(metrics['yolo_times'])
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    n, bins, patches = ax.hist(times, bins=30, color='#3498db', 
                                alpha=0.7, edgecolor='black')
    
    # Add statistics
    mean_time = np.mean(times)
    median_time = np.median(times)
    p95_time = np.percentile(times, 95)
    
    ax.axvline(mean_time, color='red', linestyle='--', linewidth=2,
               label=f'Mean: {mean_time:.1f}ms')
    ax.axvline(median_time, color='green', linestyle='--', linewidth=2,
               label=f'Median: {median_time:.1f}ms')
    ax.axvline(p95_time, color='orange', linestyle='--', linewidth=2,
               label=f'95th %ile: {p95_time:.1f}ms')
    
    ax.set_xlabel('Detection Time (ms)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Frequency', fontsize=12, fontweight='bold')
    ax.set_title(f'Real YOLO Performance Distribution\n({len(times)} actual detections from logs)',
                 fontsize=14, fontweight='bold')
    ax.legend(fontsize=11)
    ax.grid(alpha=0.3)
    
    # Add stats box
    stats_text = f'Min: {np.min(times):.1f}ms\nMax: {np.max(times):.1f}ms\nStd: {np.std(times):.1f}ms'
    ax.text(0.98, 0.97, stats_text, transform=ax.transAxes,
            fontsize=10, verticalalignment='top', horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.tight_layout()
    plt.savefig(output_dir / "real_yolo_performance.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✓ Generated: Real YOLO Performance (Mean: {mean_time:.1f}ms)")


# ============================================================================
# GRAPH 2: Component Latency Comparison (Real Data)
# ============================================================================
def plot_real_component_latency(metrics):
    """Box plot of actual component latencies"""
    
    data_to_plot = []
    labels = []
    
    if metrics['yolo_times']:
        data_to_plot.append(metrics['yolo_times'])
        labels.append(f'YOLO\n(n={len(metrics["yolo_times"])})')
    
    if metrics['vlm_times']:
        data_to_plot.append(metrics['vlm_times'])
        labels.append(f'VLM\n(n={len(metrics["vlm_times"])})')
    
    if metrics['stt_times']:
        data_to_plot.append(metrics['stt_times'])
        labels.append(f'STT\n(n={len(metrics["stt_times"])})')
    
    if metrics['llm_times']:
        data_to_plot.append(metrics['llm_times'])
        labels.append(f'LLM\n(n={len(metrics["llm_times"])})')
    
    if not data_to_plot:
        print("⚠️  No component latency data found")
        return
    
    fig, ax = plt.subplots(figsize=(12, 7))
    
    bp = ax.boxplot(data_to_plot, labels=labels, patch_artist=True,
                    showmeans=True, meanline=True)
    
    # Color boxes
    colors = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12']
    for patch, color in zip(bp['boxes'], colors[:len(bp['boxes'])]):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    
    ax.set_ylabel('Latency (milliseconds)', fontsize=12, fontweight='bold')
    ax.set_title('Real Component Latency Distribution\n(From Actual Performance Logs)',
                 fontsize=14, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)
    
    # Add mean values as text
    for i, data in enumerate(data_to_plot):
        mean_val = np.mean(data)
        ax.text(i+1, mean_val, f'{mean_val:.0f}ms',
                ha='center', va='bottom', fontweight='bold', fontsize=10)
    
    plt.tight_layout()
    plt.savefig(output_dir / "real_component_latency.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✓ Generated: Real Component Latency Comparison")


# ============================================================================
# GRAPH 3: Alert Distribution (Real Data)
# ============================================================================
def plot_real_alert_distribution(metrics):
    """Pie chart of actual alert types from logs"""
    
    if not metrics['alerts']:
        print("⚠️  No alert data found in logs")
        return
    
    from collections import Counter
    alert_counts = Counter(metrics['alerts'])
    
    labels = list(alert_counts.keys())
    sizes = list(alert_counts.values())
    
    colors_map = {
        'CRITICAL': '#e74c3c',
        'WARNING': '#f39c12',
        'INFO': '#3498db'
    }
    colors = [colors_map.get(label, '#95a5a6') for label in labels]
    
    fig, ax = plt.subplots(figsize=(10, 8))
    
    wedges, texts, autotexts = ax.pie(sizes, labels=labels, colors=colors,
                                        autopct='%1.1f%%', startangle=90,
                                        shadow=True, textprops={'fontsize': 12})
    
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontweight('bold')
    
    ax.set_title(f'Real Alert Distribution\n({sum(sizes)} total alerts from logs)',
                 fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(output_dir / "real_alert_distribution.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✓ Generated: Real Alert Distribution ({sum(sizes)} alerts)")


# ============================================================================
# GRAPH 4: Performance Over Time
# ============================================================================
def plot_performance_over_time(metrics):
    """Line graph showing performance degradation/stability"""
    
    if not metrics['yolo_times'] or len(metrics['yolo_times']) < 10:
        print("⚠️  Insufficient data for time-series analysis")
        return
    
    # Use YOLO times as proxy for overall performance
    times = np.array(metrics['yolo_times'][:500])  # First 500 samples
    
    # Calculate rolling average
    window = 20
    rolling_avg = pd.Series(times).rolling(window=window).mean()
    
    fig, ax = plt.subplots(figsize=(14, 6))
    
    ax.plot(times, alpha=0.3, color='#3498db', label='Raw Data')
    ax.plot(rolling_avg, linewidth=2, color='#e74c3c', 
            label=f'{window}-sample Moving Average')
    
    ax.set_xlabel('Sample Number', fontsize=12, fontweight='bold')
    ax.set_ylabel('YOLO Detection Time (ms)', fontsize=12, fontweight='bold')
    ax.set_title('Performance Stability Over Time\n(Real Log Data)',
                 fontsize=14, fontweight='bold')
    ax.legend(fontsize=11)
    ax.grid(alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_dir / "real_performance_timeline.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✓ Generated: Performance Timeline ({len(times)} samples)")


# ============================================================================
# Generate Summary Report
# ============================================================================
def generate_summary_report(metrics):
    """Create JSON summary of real metrics"""
    
    summary = {
        "data_source": "logs/performance.log",
        "analysis_timestamp": datetime.now().isoformat(),
        "metrics": {
            "yolo": {
                "samples": len(metrics['yolo_times']),
                "mean_ms": float(np.mean(metrics['yolo_times'])) if metrics['yolo_times'] else None,
                "median_ms": float(np.median(metrics['yolo_times'])) if metrics['yolo_times'] else None,
                "std_ms": float(np.std(metrics['yolo_times'])) if metrics['yolo_times'] else None
            },
            "vlm": {
                "samples": len(metrics['vlm_times']),
                "mean_ms": float(np.mean(metrics['vlm_times'])) if metrics['vlm_times'] else None,
                "median_ms": float(np.median(metrics['vlm_times'])) if metrics['vlm_times'] else None
            },
            "stt": {
                "samples": len(metrics['stt_times']),
                "mean_ms": float(np.mean(metrics['stt_times'])) if metrics['stt_times'] else None
            },
            "llm": {
                "samples": len(metrics['llm_times']),
                "mean_ms": float(np.mean(metrics['llm_times'])) if metrics['llm_times'] else None
            },
            "alerts": {
                "total": len(metrics['alerts']),
                "breakdown": {k: int(v) for k, v in dict(pd.Series(metrics['alerts']).value_counts()).items()} if metrics['alerts'] else {}
            }
        }
    }
    
    with open(output_dir / "real_data_summary.json", 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n✓ Summary report saved: real_data_summary.json")
    
    return summary


# ============================================================================
# MAIN EXECUTION
# ============================================================================
def main():
    # Parse logs
    metrics = parse_performance_log()
    
    if not metrics:
        print("❌ Failed to parse log file")
        return
    
    print("="*70)
    print("  Generating Graphs from Real Data...")
    print("="*70 + "\n")
    
    # Generate graphs
    plot_real_yolo_performance(metrics)
    plot_real_component_latency(metrics)
    plot_real_alert_distribution(metrics)
    plot_performance_over_time(metrics)
    
    # Generate summary
    summary = generate_summary_report(metrics)
    
    print("\n" + "="*70)
    print("✅ Real Data Analysis Complete!")
    print(f"📁 Output directory: {output_dir.absolute()}")
    print("="*70)
    
    # Print key findings
    print("\n📊 KEY FINDINGS (From Real Logs):\n")
    if metrics['yolo_times']:
        print(f"   YOLO Detection: {np.mean(metrics['yolo_times']):.1f}ms avg ({len(metrics['yolo_times'])} samples)")
    if metrics['vlm_times']:
        print(f"   VLM Inference: {np.mean(metrics['vlm_times']):.1f}ms avg ({len(metrics['vlm_times'])} samples)")
    if metrics['stt_times']:
        print(f"   STT Processing: {np.mean(metrics['stt_times']):.1f}ms avg ({len(metrics['stt_times'])} samples)")
    if metrics['alerts']:
        print(f"   Total Alerts: {len(metrics['alerts'])} events")
    
    print("\n")


if __name__ == "__main__":
    main()
