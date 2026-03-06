"""
WalkSense Prometheus Metrics Module
====================================
All custom metrics for the backend. Import this module early in server.py.

Metrics exposed:
  walksense_http_requests_total         Counter   — HTTP requests by method/path/status
  walksense_http_request_duration_seconds Histogram — HTTP request latency
  walksense_active_websocket_connections  Gauge     — live WS connections
  walksense_active_users                  Gauge     — authenticated sessions seen in last 5m
  walksense_component_latency_seconds     Histogram — per-component (vlm/llm/yolo/safety/tts/stt)
  walksense_pipeline_runs_total          Counter   — pipeline frames processed
  walksense_queries_total                Counter   — user queries submitted
  walksense_queries_failed_total         Counter   — queries that errored
  walksense_thread_pool_active           Gauge     — active threads in SystemManager
  walksense_thread_pool_blocked          Gauge     — threads blocked on CPU-intensive work
  walksense_yolo_detections_total        Counter   — total objects detected
  walksense_tts_utterances_total         Counter   — TTS utterances emitted
  walksense_auth_logins_total            Counter   — login attempts by outcome
  walksense_frame_queue_size             Gauge     — browser camera frame queue depth
"""

import threading
import time
from prometheus_client import (
    Counter, Histogram, Gauge, REGISTRY,
    generate_latest, CONTENT_TYPE_LATEST,
)

# —————————————————————————————
# HTTP Metrics
# —————————————————————————————
http_requests_total = Counter(
    "walksense_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)

http_request_duration = Histogram(
    "walksense_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# —————————————————————————————
# WebSocket / User Metrics
# —————————————————————————————
active_ws_connections = Gauge(
    "walksense_active_websocket_connections",
    "Number of active WebSocket connections (state stream)",
)

active_users_gauge = Gauge(
    "walksense_active_users",
    "Distinct authenticated users active in the last 5 minutes",
)

# —————————————————————————————
# Pipeline Component Latency
# —————————————————————————————
component_latency = Histogram(
    "walksense_component_latency_seconds",
    "End-to-end latency per pipeline component",
    ["component"],   # vlm | llm | yolo | safety | tts | stt | fusion
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

pipeline_frames_total = Counter(
    "walksense_pipeline_frames_total",
    "Total camera frames processed by the pipeline",
)

# —————————————————————————————
# Query Metrics
# —————————————————————————————
queries_total = Counter(
    "walksense_queries_total",
    "Total user queries submitted",
    ["source"],  # voice | text
)

queries_failed_total = Counter(
    "walksense_queries_failed_total",
    "User queries that resulted in an error",
    ["component"],  # stt | llm | vlm
)

# —————————————————————————————
# Thread Pool Metrics
# —————————————————————————————
thread_pool_active = Gauge(
    "walksense_thread_pool_active",
    "Active daemon threads in the SystemManager pipeline",
)

thread_pool_blocked = Gauge(
    "walksense_thread_pool_blocked",
    "Threads currently blocked on synchronous I/O or model inference",
)

# —————————————————————————————
# Detection / TTS Metrics
# —————————————————————————————
yolo_detections_total = Counter(
    "walksense_yolo_detections_total",
    "Total objects detected by YOLO",
    ["object_class"],
)

tts_utterances_total = Counter(
    "walksense_tts_utterances_total",
    "TTS utterances emitted",
    ["priority"],  # critical | warning | response | scene
)

# —————————————————————————————
# Auth Metrics
# —————————————————————————————
auth_logins_total = Counter(
    "walksense_auth_logins_total",
    "Login attempts",
    ["outcome"],  # success | failed | blocked | fallback
)

auth_registrations_total = Counter(
    "walksense_auth_registrations_total",
    "Registration attempts",
    ["outcome"],
)

# —————————————————————————————
# Camera Queue
# —————————————————————————————
frame_queue_size = Gauge(
    "walksense_frame_queue_size",
    "Number of frames waiting in the browser camera queue",
)


# —————————————————————————————
# Background thread-pool collector
# —————————————————————————————
def _update_thread_metrics():
    """Poll threading module every 10s and update thread gauges."""
    while True:
        try:
            active = sum(1 for t in threading.enumerate() if t.is_alive())
            thread_pool_active.set(active)
            # Approximation: daemon threads are pipeline workers
            blocked = sum(
                1 for t in threading.enumerate()
                if t.is_alive() and t.daemon and t.name.startswith("_")
            )
            thread_pool_blocked.set(blocked)
        except Exception:
            pass
        time.sleep(10)


_thread_collector = threading.Thread(
    target=_update_thread_metrics, daemon=True, name="metrics_collector"
)
_thread_collector.start()


def render_metrics() -> tuple[bytes, str]:
    """Return (body_bytes, content_type) for the /metrics endpoint."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
