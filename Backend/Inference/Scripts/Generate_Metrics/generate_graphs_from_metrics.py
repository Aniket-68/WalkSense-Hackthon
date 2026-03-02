"""
Generate Evaluation Graphs from Structured Metrics
Uses data from MetricsLogger JSON files for grounded, evidence-based visualizations
"""

import json
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

# Set style
sns.set_style("whitegrid")
sns.set_palette("husl")
plt.rcParams['figure.figsize'] = (12, 7)
plt.rcParams['font.size'] = 10

# Paths
metrics_dir = Path("logs/metrics")
output_dir = Path("plots/evaluation_real")
output_dir.mkdir(parents=True, exist_ok=True)

print("\n" + "="*70)
print("  WalkSense - Real Metrics Graph Generator")
print("="*70 + "\n")


def load_latest_metrics():
    """Load the most recent metrics session"""
    if not metrics_dir.exists():
        print(f"❌ Metrics directory not found: {metrics_dir}")
        return None
    
    session_files = list(metrics_dir.glob("session_*.json"))
    if not session_files:
        print(f"❌ No session files found in {metrics_dir}")
        return None
    
    latest_file = max(session_files, key=lambda p: p.stat().st_mtime)
    print(f"📂 Loading metrics from: {latest_file.name}")
    
    with open(latest_file, 'r') as f:
        metrics = json.load(f)
    
    print(f"   ✓ Loaded {len(metrics.get('detections', []))} detections")
    print(f"   ✓ Loaded {len(metrics.get('alerts', []))} alerts")
    print(f"   ✓ Loaded {len(metrics.get('queries', []))} queries\n")
    
    return metrics


# ============================================================================
# GRAPH 1: Component Latency Distribution
# ============================================================================
def plot_component_latency(metrics):
    """Box plot of component latencies"""
    data = []
    
    for component in ["yolo", "vlm", "stt", "llm"]:
        key = f"{component}_latency"
        if key in metrics and metrics[key]:
            for latency in metrics[key]:
                data.append({
                    "Component": component.upper(),
                    "Latency (ms)": latency
                })
    
    if not data:
        print("⚠️  No latency data available")
        return
    
    df = pd.DataFrame(data)
    
    fig, ax = plt.subplots(figsize=(12, 7))
    
    bp = sns.boxplot(x="Component", y="Latency (ms)", data=df, ax=ax)
    
    # Add mean markers
    means = df.groupby("Component")["Latency (ms)"].mean()
    positions = range(len(means))
    ax.scatter(positions, means.values, color='red', s=100, zorder=3, 
               label='Mean', marker='D')
    
    ax.set_title("Component Latency Distribution (Real Data)", 
                 fontsize=14, fontweight='bold')
    ax.set_ylabel("Latency (milliseconds)", fontweight='bold')
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    # Add sample counts
    for i, (comp, group) in enumerate(df.groupby("Component")):
        count = len(group)
        mean_val = means[comp]
        ax.text(i, mean_val, f'n={count}', ha='center', va='bottom', 
                fontsize=9, fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(output_dir / "01_component_latency.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✓ Generated: Component Latency Distribution")


# ============================================================================
# GRAPH 2: YOLO Performance Timeline
# ============================================================================
def plot_yolo_timeline(metrics):
    """Line graph of YOLO latency over time"""
    if not metrics.get("yolo_latency"):
        print("⚠️  No YOLO latency data")
        return
    
    latencies = metrics["yolo_latency"]
    
    fig, ax = plt.subplots(figsize=(14, 6))
    
    # Plot raw data
    ax.plot(latencies, alpha=0.3, color='#3498db', linewidth=0.5, label='Raw')
    
    # Plot moving average
    window = min(20, len(latencies) // 10)
    if window > 1:
        moving_avg = pd.Series(latencies).rolling(window=window).mean()
        ax.plot(moving_avg, color='#e74c3c', linewidth=2, 
                label=f'{window}-sample Moving Average')
    
    # Add statistics
    mean_lat = np.mean(latencies)
    ax.axhline(mean_lat, color='green', linestyle='--', linewidth=2,
               label=f'Mean: {mean_lat:.1f}ms')
    
    ax.set_xlabel("Sample Number", fontweight='bold')
    ax.set_ylabel("YOLO Latency (ms)", fontweight='bold')
    ax.set_title(f"YOLO Performance Over Time ({len(latencies)} samples)", 
                 fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_dir / "02_yolo_timeline.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✓ Generated: YOLO Performance Timeline")


# ============================================================================
# GRAPH 3: Alert Distribution
# ============================================================================
def plot_alert_distribution(metrics):
    """Pie chart of alert types"""
    if not metrics.get("alerts"):
        print("⚠️  No alert data")
        return
    
    alerts = metrics["alerts"]
    
    # Count by type
    types = [a["type"] for a in alerts if not a.get("suppressed", False)]
    
    if not types:
        print("⚠️  No active alerts (all suppressed)")
        return
    
    from collections import Counter
    type_counts = Counter(types)
    
    # Create pie chart
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    
    # Active alerts
    labels = list(type_counts.keys())
    sizes = list(type_counts.values())
    colors = {'CRITICAL_ALERT': '#e74c3c', 'WARNING': '#f39c12', 'INFO': '#3498db'}
    pie_colors = [colors.get(label, '#95a5a6') for label in labels]
    
    wedges, texts, autotexts = ax1.pie(sizes, labels=labels, colors=pie_colors,
                                         autopct='%1.1f%%', startangle=90,
                                         textprops={'fontsize': 11, 'fontweight': 'bold'})
    
    for autotext in autotexts:
        autotext.set_color('white')
    
    ax1.set_title(f'Active Alerts Distribution\n({sum(sizes)} total)', 
                  fontsize=13, fontweight='bold')
    
    # Suppression effectiveness
    total_alerts = len(alerts)
    suppressed = sum(1 for a in alerts if a.get("suppressed", False))
    active = total_alerts - suppressed
    
    ax2.bar(['Active', 'Suppressed'], [active, suppressed], 
            color=['#2ecc71', '#95a5a6'], alpha=0.7, edgecolor='black')
    ax2.set_ylabel("Count", fontweight='bold')
    ax2.set_title(f'Redundancy Filter Effectiveness\n({suppressed/total_alerts*100:.1f}% reduction)', 
                  fontsize=13, fontweight='bold')
    ax2.grid(axis='y', alpha=0.3)
    
    # Add counts on bars
    for i, v in enumerate([active, suppressed]):
        ax2.text(i, v, str(v), ha='center', va='bottom', fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(output_dir / "03_alert_distribution.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✓ Generated: Alert Distribution ({suppressed/total_alerts*100:.1f}% suppressed)")


# ============================================================================
# GRAPH 4: Detection Frequency
# ============================================================================
def plot_detection_frequency(metrics):
    """Bar chart of detected objects"""
    if not metrics.get("detections"):
        print("⚠️  No detection data")
        return
    
    detections = metrics["detections"]
    labels = [d["label"] for d in detections]
    
    from collections import Counter
    label_counts = Counter(labels)
    
    # Sort by frequency
    sorted_labels = sorted(label_counts.items(), key=lambda x: x[1], reverse=True)
    top_labels = sorted_labels[:15]  # Top 15
    
    objects = [item[0] for item in top_labels]
    counts = [item[1] for item in top_labels]
    
    fig, ax = plt.subplots(figsize=(12, 7))
    
    bars = ax.barh(objects, counts, color='#3498db', alpha=0.7, edgecolor='black')
    
    # Color code by safety level
    critical = {'car', 'knife', 'gun', 'fire', 'scissors'}
    warning = {'pole', 'stairs', 'dog', 'bicycle', 'motorcycle'}
    
    for bar, obj in zip(bars, objects):
        if obj in critical:
            bar.set_color('#e74c3c')
        elif obj in warning:
            bar.set_color('#f39c12')
    
    ax.set_xlabel("Detection Count", fontweight='bold')
    ax.set_title(f"Object Detection Frequency (Top 15)\n{len(detections)} total detections", 
                 fontsize=14, fontweight='bold')
    ax.grid(axis='x', alpha=0.3)
    
    # Add counts on bars
    for i, v in enumerate(counts):
        ax.text(v, i, f' {v}', va='center', fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(output_dir / "04_detection_frequency.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✓ Generated: Detection Frequency ({len(label_counts)} unique objects)")


# ============================================================================
# GRAPH 5: Query Response Time
# ============================================================================
def plot_query_response(metrics):
    """Histogram of query response times"""
    if not metrics.get("queries"):
        print("⚠️  No query data")
        return
    
    queries = metrics["queries"]
    response_times = [q["response_time_ms"] for q in queries]
    vlm_used = [q.get("vlm_used", False) for q in queries]
    
    fig, ax = plt.subplots(figsize=(12, 7))
    
    # Separate by VLM usage
    with_vlm = [rt for rt, vlm in zip(response_times, vlm_used) if vlm]
    without_vlm = [rt for rt, vlm in zip(response_times, vlm_used) if not vlm]
    
    if with_vlm:
        ax.hist(with_vlm, bins=20, alpha=0.6, label=f'With VLM (n={len(with_vlm)})',
                color='#e74c3c', edgecolor='black')
    if without_vlm:
        ax.hist(without_vlm, bins=20, alpha=0.6, label=f'Without VLM (n={len(without_vlm)})',
                color='#3498db', edgecolor='black')
    
    # Add statistics
    mean_time = np.mean(response_times)
    ax.axvline(mean_time, color='green', linestyle='--', linewidth=2,
               label=f'Mean: {mean_time:.0f}ms')
    
    ax.set_xlabel("Response Time (ms)", fontweight='bold')
    ax.set_ylabel("Frequency", fontweight='bold')
    ax.set_title(f"Query Response Time Distribution ({len(queries)} queries)", 
                 fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_dir / "05_query_response.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✓ Generated: Query Response Distribution")


# ============================================================================
# GRAPH 6: FPS Stability
# ============================================================================
def plot_fps_stability(metrics):
    """Line graph of FPS over time"""
    if not metrics.get("fps_samples"):
        print("⚠️  No FPS data")
        return
    
    fps_samples = metrics["fps_samples"]
    timestamps = [s["timestamp"] for s in fps_samples]
    fps_values = [s["fps"] for s in fps_samples]
    
    fig, ax = plt.subplots(figsize=(14, 6))
    
    ax.plot(timestamps, fps_values, color='#2ecc71', linewidth=1.5, alpha=0.7)
    ax.fill_between(timestamps, fps_values, alpha=0.3, color='#2ecc71')
    
    # Add target line
    target_fps = 30
    ax.axhline(target_fps, color='red', linestyle='--', linewidth=2,
               label=f'Target: {target_fps} FPS')
    
    # Add mean
    mean_fps = np.mean(fps_values)
    ax.axhline(mean_fps, color='blue', linestyle='--', linewidth=2,
               label=f'Mean: {mean_fps:.1f} FPS')
    
    ax.set_xlabel("Time (seconds)", fontweight='bold')
    ax.set_ylabel("FPS", fontweight='bold')
    ax.set_title(f"System Throughput Stability ({len(fps_samples)} samples)", 
                 fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_dir / "06_fps_stability.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✓ Generated: FPS Stability (Mean: {mean_fps:.1f})")


# ============================================================================
# GRAPH 7: Spatial Direction Accuracy
# ============================================================================
def plot_spatial_accuracy(metrics):
    """Bar chart of spatial direction accuracy"""
    if not metrics.get("spatial_predictions"):
        print("⚠️  No spatial prediction data")
        return
    
    predictions = [p for p in metrics["spatial_predictions"] if p.get("correct") is not None]
    
    if not predictions:
        print("⚠️  No ground truth spatial data")
        return
    
    # Count by direction
    directions = ["left", "center", "right"]
    accuracy_by_dir = {}
    
    for direction in directions:
        dir_preds = [p for p in predictions if p["predicted"] == direction]
        if dir_preds:
            correct = sum(1 for p in dir_preds if p["correct"])
            accuracy_by_dir[direction] = (correct / len(dir_preds)) * 100
        else:
            accuracy_by_dir[direction] = 0
    
    fig, ax = plt.subplots(figsize=(10, 7))
    
    dirs = list(accuracy_by_dir.keys())
    accs = list(accuracy_by_dir.values())
    
    bars = ax.bar(dirs, accs, color=['#3498db', '#2ecc71', '#f39c12'], 
                  alpha=0.7, edgecolor='black')
    
    ax.set_ylabel("Accuracy (%)", fontweight='bold')
    ax.set_title(f"Spatial Direction Detection Accuracy\n({len(predictions)} predictions)", 
                 fontsize=14, fontweight='bold')
    ax.set_ylim(0, 105)
    ax.grid(axis='y', alpha=0.3)
    
    # Add percentage labels
    for bar, acc in zip(bars, accs):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{acc:.1f}%', ha='center', va='bottom', fontweight='bold', fontsize=12)
    
    # Add overall accuracy
    overall_acc = sum(1 for p in predictions if p["correct"]) / len(predictions) * 100
    ax.axhline(overall_acc, color='red', linestyle='--', linewidth=2,
               label=f'Overall: {overall_acc:.1f}%')
    ax.legend()
    
    plt.tight_layout()
    plt.savefig(output_dir / "07_spatial_accuracy.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✓ Generated: Spatial Accuracy ({overall_acc:.1f}% overall)")


# ============================================================================
# GRAPH 8: GPU Memory Usage
# ============================================================================
def plot_gpu_memory(metrics):
    """Line graph of GPU memory usage over time"""
    if not metrics.get("gpu_memory"):
        print("⚠️  No GPU memory data")
        return
    
    mem_samples = metrics["gpu_memory"]
    timestamps = [s["timestamp"] for s in mem_samples]
    used_mb = [s["used_mb"] for s in mem_samples]
    total_mb = mem_samples[0]["total_mb"] if mem_samples else 8192
    
    fig, ax = plt.subplots(figsize=(14, 6))
    
    ax.plot(timestamps, used_mb, color='#9b59b6', linewidth=2, label='Used Memory')
    ax.fill_between(timestamps, used_mb, alpha=0.3, color='#9b59b6')
    
    # Add total line
    ax.axhline(total_mb, color='red', linestyle='--', linewidth=2,
               label=f'Total: {total_mb:.0f} MB')
    
    # Add mean
    mean_used = np.mean(used_mb)
    ax.axhline(mean_used, color='green', linestyle='--', linewidth=2,
               label=f'Mean: {mean_used:.0f} MB ({mean_used/total_mb*100:.1f}%)')
    
    ax.set_xlabel("Time (seconds)", fontweight='bold')
    ax.set_ylabel("Memory (MB)", fontweight='bold')
    ax.set_title(f"GPU Memory Usage Over Time ({len(mem_samples)} samples)", 
                 fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_dir / "08_gpu_memory.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✓ Generated: GPU Memory Usage (Mean: {mean_used:.0f}MB)")


# ============================================================================
# Main Execution
# ============================================================================
def main():
    metrics = load_latest_metrics()
    
    if not metrics:
        print("\n❌ No metrics data available. Run the system with MetricsLogger first.\n")
        return
    
    print("="*70)
    print("  Generating Evaluation Graphs...")
    print("="*70 + "\n")
    
    # Generate all graphs
    plot_component_latency(metrics)
    plot_yolo_timeline(metrics)
    plot_alert_distribution(metrics)
    plot_detection_frequency(metrics)
    plot_query_response(metrics)
    plot_fps_stability(metrics)
    plot_spatial_accuracy(metrics)
    plot_gpu_memory(metrics)
    
    print("\n" + "="*70)
    print(f"✅ All graphs generated successfully!")
    print(f"📁 Output directory: {output_dir.absolute()}")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
