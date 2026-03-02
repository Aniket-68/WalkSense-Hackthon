"""
Enhanced Metrics Logger for WalkSense Evaluation
Captures detailed performance data for generating grounded evaluation graphs
"""

import json
import time
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from loguru import logger
import numpy as np


class MetricsLogger:
    """
    Comprehensive metrics logger that captures:
    - Component latencies (YOLO, VLM, STT, LLM)
    - Detection accuracy (TP, FP, FN)
    - Alert events with severity
    - Query response times
    - GPU memory usage
    - Spatial accuracy
    - System throughput (FPS)
    """
    
    def __init__(self, output_dir="logs/metrics"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Session metadata
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_start = time.time()
        
        # Metrics storage
        self.metrics = {
            # Component latencies
            "yolo_latency": [],
            "vlm_latency": [],
            "stt_latency": [],
            "llm_latency": [],
            "frame_latency": [],
            
            # Detection metrics
            "detections": [],  # {timestamp, label, confidence, bbox, direction}
            "ground_truth": [],  # For accuracy calculation
            
            # Alert metrics
            "alerts": [],  # {timestamp, type, severity, message, suppressed}
            
            # Query metrics
            "queries": [],  # {timestamp, query, response_time, vlm_used}
            
            # System metrics
            "fps_samples": [],
            "gpu_memory": [],  # {timestamp, used_mb, total_mb}
            
            # Spatial accuracy
            "spatial_predictions": [],  # {timestamp, object, predicted_dir, actual_dir}
        }
        
        # Timers
        self.timers = {}
        
        logger.info(f"📊 Metrics Logger initialized: Session {self.session_id}")
    
    # ============================================================================
    # Timer Methods
    # ============================================================================
    
    def start_timer(self, component: str):
        """Start timing a component"""
        self.timers[component] = time.time()
    
    def stop_timer(self, component: str) -> float:
        """Stop timer and log latency in milliseconds"""
        if component not in self.timers:
            return 0.0
        
        duration_ms = (time.time() - self.timers[component]) * 1000
        del self.timers[component]
        
        # Store in appropriate metric
        if component == "yolo":
            self.metrics["yolo_latency"].append(duration_ms)
            logger.debug(f"⏱️  YOLO: {duration_ms:.1f}ms")
        elif component == "vlm":
            self.metrics["vlm_latency"].append(duration_ms)
            logger.info(f"⏱️  VLM: {duration_ms/1000:.2f}s")
        elif component == "stt":
            self.metrics["stt_latency"].append(duration_ms)
            logger.info(f"⏱️  STT: {duration_ms/1000:.2f}s")
        elif component == "llm":
            self.metrics["llm_latency"].append(duration_ms)
            logger.info(f"⏱️  LLM: {duration_ms/1000:.2f}s")
        elif component == "frame":
            self.metrics["frame_latency"].append(duration_ms)
        
        return duration_ms
    
    # ============================================================================
    # Detection Logging
    # ============================================================================
    
    def log_detection(self, label: str, confidence: float, bbox: list, 
                     direction: str = None, frame_width: int = 1280):
        """Log object detection"""
        # Calculate direction if not provided
        if direction is None and bbox:
            x_center = (bbox[0] + bbox[2]) / 2
            if x_center < frame_width * 0.33:
                direction = "left"
            elif x_center < frame_width * 0.66:
                direction = "center"
            else:
                direction = "right"
        
        self.metrics["detections"].append({
            "timestamp": time.time() - self.session_start,
            "label": label,
            "confidence": confidence,
            "bbox": bbox,
            "direction": direction
        })
    
    def log_detection_batch(self, detections: list, frame_width: int = 1280):
        """Log multiple detections at once"""
        for det in detections:
            self.log_detection(
                label=det.get("label"),
                confidence=det.get("confidence", 0.0),
                bbox=det.get("bbox", []),
                frame_width=frame_width
            )
    
    # ============================================================================
    # Alert Logging
    # ============================================================================
    
    def log_alert(self, alert_type: str, severity: str, message: str, 
                  suppressed: bool = False):
        """
        Log safety alert
        
        Args:
            alert_type: "CRITICAL_ALERT", "WARNING", "INFO"
            severity: "high", "medium", "low"
            message: Alert message
            suppressed: Whether redundancy filter suppressed it
        """
        self.metrics["alerts"].append({
            "timestamp": time.time() - self.session_start,
            "type": alert_type,
            "severity": severity,
            "message": message,
            "suppressed": suppressed
        })
        
        if not suppressed:
            logger.warning(f"🚨 Alert [{alert_type}]: {message}")
    
    # ============================================================================
    # Query Logging
    # ============================================================================
    
    def log_query(self, query: str, response_time_ms: float, vlm_used: bool = False):
        """Log user query and response time"""
        self.metrics["queries"].append({
            "timestamp": time.time() - self.session_start,
            "query": query,
            "response_time_ms": response_time_ms,
            "vlm_used": vlm_used
        })
        
        logger.info(f"❓ Query: '{query}' | Response: {response_time_ms:.0f}ms | VLM: {vlm_used}")
    
    # ============================================================================
    # System Metrics
    # ============================================================================
    
    def log_fps(self, fps: float):
        """Log current FPS"""
        self.metrics["fps_samples"].append({
            "timestamp": time.time() - self.session_start,
            "fps": fps
        })
    
    def log_gpu_memory(self, used_mb: float, total_mb: float):
        """Log GPU memory usage"""
        self.metrics["gpu_memory"].append({
            "timestamp": time.time() - self.session_start,
            "used_mb": used_mb,
            "total_mb": total_mb,
            "usage_percent": (used_mb / total_mb * 100) if total_mb > 0 else 0
        })
    
    # ============================================================================
    # Spatial Accuracy
    # ============================================================================
    
    def log_spatial_prediction(self, object_label: str, predicted_dir: str, 
                               actual_dir: str = None):
        """
        Log spatial direction prediction
        
        Args:
            object_label: Detected object
            predicted_dir: "left", "center", "right"
            actual_dir: Ground truth direction (if available)
        """
        self.metrics["spatial_predictions"].append({
            "timestamp": time.time() - self.session_start,
            "object": object_label,
            "predicted": predicted_dir,
            "actual": actual_dir,
            "correct": predicted_dir == actual_dir if actual_dir else None
        })
    
    # ============================================================================
    # Statistics & Summary
    # ============================================================================
    
    def get_summary(self) -> dict:
        """Get comprehensive metrics summary"""
        summary = {
            "session_id": self.session_id,
            "duration_seconds": time.time() - self.session_start,
            "components": {},
            "detections": {},
            "alerts": {},
            "queries": {},
            "system": {}
        }
        
        # Component latencies
        for component in ["yolo", "vlm", "stt", "llm", "frame"]:
            key = f"{component}_latency"
            if self.metrics[key]:
                values = self.metrics[key]
                summary["components"][component] = {
                    "count": len(values),
                    "mean_ms": float(np.mean(values)),
                    "median_ms": float(np.median(values)),
                    "std_ms": float(np.std(values)),
                    "min_ms": float(np.min(values)),
                    "max_ms": float(np.max(values)),
                    "p95_ms": float(np.percentile(values, 95))
                }
        
        # Detection stats
        if self.metrics["detections"]:
            labels = [d["label"] for d in self.metrics["detections"]]
            unique_labels = set(labels)
            summary["detections"] = {
                "total": len(labels),
                "unique_objects": len(unique_labels),
                "breakdown": {label: labels.count(label) for label in unique_labels}
            }
        
        # Alert stats
        if self.metrics["alerts"]:
            alerts = self.metrics["alerts"]
            summary["alerts"] = {
                "total": len(alerts),
                "suppressed": sum(1 for a in alerts if a["suppressed"]),
                "active": sum(1 for a in alerts if not a["suppressed"]),
                "by_type": {
                    "CRITICAL": sum(1 for a in alerts if a["type"] == "CRITICAL_ALERT"),
                    "WARNING": sum(1 for a in alerts if a["type"] == "WARNING"),
                    "INFO": sum(1 for a in alerts if a["type"] == "INFO")
                }
            }
        
        # Query stats
        if self.metrics["queries"]:
            queries = self.metrics["queries"]
            response_times = [q["response_time_ms"] for q in queries]
            summary["queries"] = {
                "total": len(queries),
                "mean_response_ms": float(np.mean(response_times)),
                "vlm_used_count": sum(1 for q in queries if q["vlm_used"])
            }
        
        # System stats
        if self.metrics["fps_samples"]:
            fps_values = [s["fps"] for s in self.metrics["fps_samples"]]
            summary["system"]["fps"] = {
                "mean": float(np.mean(fps_values)),
                "min": float(np.min(fps_values)),
                "max": float(np.max(fps_values))
            }
        
        if self.metrics["gpu_memory"]:
            mem_samples = self.metrics["gpu_memory"]
            usage_pcts = [m["usage_percent"] for m in mem_samples]
            summary["system"]["gpu_memory"] = {
                "mean_usage_percent": float(np.mean(usage_pcts)),
                "peak_usage_mb": float(max(m["used_mb"] for m in mem_samples))
            }
        
        # Spatial accuracy
        if self.metrics["spatial_predictions"]:
            preds = [p for p in self.metrics["spatial_predictions"] if p["correct"] is not None]
            if preds:
                correct = sum(1 for p in preds if p["correct"])
                summary["spatial_accuracy"] = {
                    "total_predictions": len(preds),
                    "correct": correct,
                    "accuracy_percent": (correct / len(preds) * 100)
                }
        
        return summary
    
    # ============================================================================
    # Export Methods
    # ============================================================================
    
    def save_metrics(self):
        """Save all metrics to JSON file"""
        output_file = self.output_dir / f"session_{self.session_id}.json"
        
        with open(output_file, 'w') as f:
            json.dump(self.metrics, f, indent=2)
        
        logger.info(f"💾 Metrics saved: {output_file}")
        return output_file
    
    def save_summary(self):
        """Save summary statistics"""
        summary = self.get_summary()
        output_file = self.output_dir / f"summary_{self.session_id}.json"
        
        with open(output_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"📈 Summary saved: {output_file}")
        return output_file
    
    def print_summary(self):
        """Print summary to console"""
        summary = self.get_summary()
        
        print("\n" + "="*70)
        print(f"  WalkSense Metrics Summary - Session {self.session_id}")
        print("="*70)
        print(f"\n⏱️  Duration: {summary['duration_seconds']:.1f}s\n")
        
        # Components
        if summary.get("components"):
            print("🔧 Component Latencies:")
            for comp, stats in summary["components"].items():
                print(f"   {comp.upper():8s}: {stats['mean_ms']:6.1f}ms avg "
                      f"({stats['min_ms']:.0f}-{stats['max_ms']:.0f}ms, "
                      f"n={stats['count']})")
        
        # Detections
        if summary.get("detections"):
            det = summary["detections"]
            print(f"\n👁️  Detections: {det['total']} total, {det['unique_objects']} unique objects")
        
        # Alerts
        if summary.get("alerts"):
            alert = summary["alerts"]
            print(f"\n🚨 Alerts: {alert['active']} active, {alert['suppressed']} suppressed "
                  f"({alert['suppressed']/(alert['total'])*100:.1f}% reduction)")
        
        # Queries
        if summary.get("queries"):
            q = summary["queries"]
            print(f"\n❓ Queries: {q['total']} total, {q['mean_response_ms']:.0f}ms avg response")
        
        # System
        if summary.get("system"):
            sys = summary["system"]
            if "fps" in sys:
                print(f"\n📊 FPS: {sys['fps']['mean']:.1f} avg "
                      f"({sys['fps']['min']:.1f}-{sys['fps']['max']:.1f})")
            if "gpu_memory" in sys:
                print(f"   GPU: {sys['gpu_memory']['mean_usage_percent']:.1f}% avg, "
                      f"{sys['gpu_memory']['peak_usage_mb']:.0f}MB peak")
        
        # Spatial accuracy
        if summary.get("spatial_accuracy"):
            spa = summary["spatial_accuracy"]
            print(f"\n🎯 Spatial Accuracy: {spa['accuracy_percent']:.1f}% "
                  f"({spa['correct']}/{spa['total_predictions']})")
        
        print("\n" + "="*70 + "\n")


# Global instance
metrics_logger = MetricsLogger()
