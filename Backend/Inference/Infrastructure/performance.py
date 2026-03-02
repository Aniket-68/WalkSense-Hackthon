# utils/performance_tracker.py
import time
import collections
from loguru import logger
import os

class PerformanceTracker:
    """
    Utility for tracking and logging performance metrics across the pipeline.
    """
    def __init__(self, log_to_file=True):
        self.metrics = collections.defaultdict(list)
        self.start_times = {}
        
        # Remove default terminal logging (ID 0)
        import sys
        try:
            logger.remove(0) 
        except:
            pass
        
        # Add a clean terminal logger for interactions only
        logger.add(
            sys.stderr, 
            format="<cyan>WalkSense</cyan> | <level>{message}</level>", 
            filter=lambda record: any(kw in record["message"] for kw in ["USER:", "AI:", "Safety Alert:", "System"]),
            level="INFO"
        )
        
        if log_to_file:
            os.makedirs("logs", exist_ok=True)
            logger.add("logs/performance.log", rotation="10 MB", level="INFO")

    def start_timer(self, name):
        """Starts a timer for a specific component."""
        self.start_times[name] = time.time()

    def stop_timer(self, name):
        """Stops a timer and records the duration."""
        if name in self.start_times:
            duration = (time.time() - self.start_times[name]) * 1000  # ms
            self.metrics[name].append(duration)
            del self.start_times[name]
            
            # Log as needed
            if duration > 500: # Log heavy operations (VLM, LLM)
                logger.info(f"{name.upper()} took {duration/1000:.2f}s")
            return duration
        return 0

    def get_summary(self):
        """Returns averages and statistics for all tracked metrics."""
        summary = {}
        for name, values in self.metrics.items():
            if not values: continue
            avg = sum(values) / len(values)
            summary[name] = {
                "avg_ms": avg,
                "max_ms": max(values),
                "min_ms": min(values),
                "count": len(values)
            }
        return summary

    def plot_metrics(self, output_path="plots/performance_summary.png"):
        """Generates a performance visualization chart."""
        try:
            import matplotlib.pyplot as plt
            import seaborn as sns
            import pandas as pd
            
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Prepare data for plotting
            data = []
            for name, values in self.metrics.items():
                for v in values:
                    data.append({"Component": name, "Latency (ms)": v})
            
            if not data:
                logger.warning("No performance data to plot.")
                return

            df = pd.DataFrame(data)
            
            plt.figure(figsize=(12, 6))
            sns.set_theme(style="whitegrid")
            
            # Boxplot for distribution
            ax = sns.boxplot(x="Component", y="Latency (ms)", data=df, palette="viridis")
            plt.title("WalkSense Component Latency Distribution", fontsize=16)
            plt.yscale("log") # VLM vs YOLO differences are huge
            
            plt.savefig(output_path)
            plt.close()
            logger.info(f"Performance plot saved to {output_path}")
            
        except Exception as e:
            logger.error(f"Failed to generate plot: {e}")

    def clear(self):
        """Resets all metrics."""
        self.metrics.clear()
        self.start_times.clear()

# Global tracker instance
tracker = PerformanceTracker()
