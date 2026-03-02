# perception/depth_estimator.py

"""
Monocular Depth Estimation for WalkSense AI.

Supports multiple depth models:
  - Depth Anything V2 (Small / Base)  — fast, accurate, recommended
  - MiDaS (DPT-Hybrid / DPT-Large)   — classic, well-tested

Provides:
  - Per-pixel relative depth maps
  - Object-level depth estimation (via bounding boxes)
  - Metric distance bucketing ("very close", "close", etc.)
"""

import cv2
import numpy as np
import torch
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from loguru import logger


class DepthEstimator:
    """
    Monocular depth estimation powered by transformer models.
    Loads configuration from config.json via Infrastructure.config.
    """

    # Distance buckets (relative depth normalised 0-1, lower = closer)
    DISTANCE_THRESHOLDS = {
        "very close": 0.75,   # top 25% of depth intensity (closest)
        "close":      0.55,
        "medium":     0.35,
        "far":        0.0,
    }

    def __init__(self, model_key: Optional[str] = None, device: Optional[str] = None):
        """
        Args:
            model_key: Key into config.json depth.models (e.g. "depth_anything_v2_small").
                       If None, uses depth.active_model from config.
            device:    Force device ("cuda" / "cpu"). If None, reads from config.
        """
        from Infrastructure.config import Config

        self.enabled = Config.get("depth.enabled", True)
        if not self.enabled:
            logger.warning("[DEPTH] Depth estimation disabled in config")
            self.model = None
            return

        model_key = model_key or Config.get("depth.active_model", "depth_anything_v2_small")
        cfg_path = f"depth.models.{model_key}"

        self.model_id   = Config.get(f"{cfg_path}.model_id", "depth-anything/Depth-Anything-V2-Small")
        local_path      = Config.get(f"{cfg_path}.local_model_path", "")
        self.model_type = Config.get(f"{cfg_path}.type", "huggingface")
        self.max_fps    = Config.get("depth.max_fps", 10)

        # Device
        requested = device or Config.get(f"{cfg_path}.device", "cuda")
        if requested == "cuda" and not torch.cuda.is_available():
            logger.warning("[DEPTH] CUDA requested but unavailable — falling back to CPU")
            requested = "cpu"
        self.device = requested

        # Resolve local path (relative to Inference/ root)
        inference_root = Path(__file__).resolve().parent.parent
        self.local_dir = inference_root / local_path if local_path else None

        # Load model
        self.model = None
        self.processor = None
        self._load_model()

        # Throttle state
        self._last_run = 0.0
        self._cached_depth: Optional[np.ndarray] = None

    # ── Model loading ────────────────────────────────────────────────────────
    def _load_model(self):
        """Load the depth model and processor from HuggingFace or local dir."""
        try:
            from transformers import AutoImageProcessor, AutoModelForDepthEstimation

            source = str(self.local_dir) if (self.local_dir and self.local_dir.exists() and any(self.local_dir.iterdir())) else self.model_id

            logger.info(f"[DEPTH] Loading model from: {source}")
            self.processor = AutoImageProcessor.from_pretrained(source)
            self.model = AutoModelForDepthEstimation.from_pretrained(source).to(self.device)
            self.model.eval()
            logger.info(f"[DEPTH] Model loaded on {self.device}")

        except Exception as e:
            logger.error(f"[DEPTH] Failed to load depth model: {e}")
            self.model = None

    # ── Core inference ───────────────────────────────────────────────────────
    def estimate(self, frame: np.ndarray, force: bool = False) -> Optional[np.ndarray]:
        """
        Compute a relative depth map for the given BGR frame.

        Returns:
            H×W float32 numpy array (0-1 normalised, higher = closer) or None.
        """
        if self.model is None:
            return self._cached_depth

        # Throttle
        now = time.time()
        if not force and (now - self._last_run) < (1.0 / self.max_fps):
            return self._cached_depth

        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            from PIL import Image
            pil_img = Image.fromarray(rgb)

            inputs = self.processor(images=pil_img, return_tensors="pt").to(self.device)

            with torch.no_grad():
                outputs = self.model(**inputs)
                depth = outputs.predicted_depth  # (1, H', W')

            # Interpolate to original size
            depth = torch.nn.functional.interpolate(
                depth.unsqueeze(1),
                size=frame.shape[:2],
                mode="bicubic",
                align_corners=False,
            ).squeeze().cpu().numpy()

            # Normalise 0-1 (higher = closer)
            d_min, d_max = depth.min(), depth.max()
            if d_max - d_min > 1e-6:
                depth_norm = (depth - d_min) / (d_max - d_min)
            else:
                depth_norm = np.zeros_like(depth)

            self._cached_depth = depth_norm.astype(np.float32)
            self._last_run = now
            return self._cached_depth

        except Exception as e:
            logger.error(f"[DEPTH] Inference failed: {e}")
            return self._cached_depth

    # ── Object-level helpers ─────────────────────────────────────────────────
    def get_object_depth(self, depth_map: np.ndarray, bbox: List[float]) -> float:
        """
        Get mean relative depth for the centre region of a bounding box.

        Args:
            depth_map: H×W float32 normalised depth map.
            bbox:      [x1, y1, x2, y2] pixel coordinates.

        Returns:
            Mean depth value (0-1, higher = closer).
        """
        h, w = depth_map.shape[:2]
        x1, y1, x2, y2 = [int(c) for c in bbox]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        # Use inner 50 % of the bbox to avoid boundary noise
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        rw, rh = max(1, (x2 - x1) // 4), max(1, (y2 - y1) // 4)
        roi = depth_map[max(0, cy - rh):min(h, cy + rh), max(0, cx - rw):min(w, cx + rw)]

        if roi.size == 0:
            return 0.0
        return float(np.mean(roi))

    def classify_distance(self, depth_value: float) -> str:
        """
        Convert normalised depth value to human distance label.

        Args:
            depth_value: 0-1, higher = closer.

        Returns:
            "very close" | "close" | "medium" | "far"
        """
        for label, threshold in self.DISTANCE_THRESHOLDS.items():
            if depth_value >= threshold:
                return label
        return "far"

    def get_object_distance(self, depth_map: np.ndarray, bbox: List[float]) -> Tuple[float, str]:
        """
        Convenience: returns (raw_depth, distance_label) for one bbox.
        """
        raw = self.get_object_depth(depth_map, bbox)
        return raw, self.classify_distance(raw)

    # ── Visualisation ────────────────────────────────────────────────────────
    def colorize(self, depth_map: np.ndarray) -> np.ndarray:
        """
        Convert depth map to a colour-mapped BGR image for visualisation.
        """
        depth_uint8 = (depth_map * 255).astype(np.uint8)
        return cv2.applyColorMap(depth_uint8, cv2.COLORMAP_INFERNO)

    # ── Status ───────────────────────────────────────────────────────────────
    @property
    def is_ready(self) -> bool:
        return self.model is not None
