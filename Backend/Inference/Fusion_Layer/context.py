# inference/spatial_context_manager.py

import numpy as np
import time
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

@dataclass
class ObjectState:
    """Represents a tracked object with spatial-temporal information"""
    track_id: int
    label: str
    bbox: List[float]  # [x1, y1, x2, y2]
    confidence: float
    timestamp: float
    
    # Spatial information
    center: np.ndarray = field(default_factory=lambda: np.zeros(2))
    distance: float = 0.0  # Estimated distance from user
    direction: str = ""  # "center", "left", "right"
    
    # Temporal information
    first_seen: float = 0.0
    frames_tracked: int = 0
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(2))  # pixels/sec
    
    def __post_init__(self):
        # Calculate center from bbox
        self.center = np.array([
            (self.bbox[0] + self.bbox[2]) / 2,
            (self.bbox[1] + self.bbox[3]) / 2
        ])
        
        if self.first_seen == 0.0:
            self.first_seen = self.timestamp


class IOUTracker:
    """Simple IoU-based object tracker"""
    
    def __init__(self, iou_threshold=0.3, max_age=30):
        self.iou_threshold = iou_threshold
        self.max_age = max_age  # frames
        self.next_id = 0
        self.tracks: Dict[int, ObjectState] = {}
        self.ages: Dict[int, int] = {}
        
    def _compute_iou(self, box1, box2):
        """Compute IoU between two boxes [x1, y1, x2, y2]"""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        
        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0
    
    def update(self, detections: List[Dict], timestamp: float) -> Dict[int, ObjectState]:
        """
        Update tracks with new detections
        
        Args:
            detections: List of detection dicts with 'bbox', 'label', 'confidence'
            timestamp: Current timestamp
            
        Returns:
            Dict mapping track_id to ObjectState
        """
        # Age all tracks
        for track_id in list(self.ages.keys()):
            self.ages[track_id] += 1
            if self.ages[track_id] > self.max_age:
                del self.tracks[track_id]
                del self.ages[track_id]
        
        # Match detections to existing tracks
        matched_tracks = set()
        matched_detections = set()
        
        for det_idx, det in enumerate(detections):
            best_iou = 0
            best_track_id = None
            
            for track_id, track in self.tracks.items():
                if track.label != det['label']:
                    continue
                    
                iou = self._compute_iou(det['bbox'][0], track.bbox)
                if iou > best_iou and iou > self.iou_threshold:
                    best_iou = iou
                    best_track_id = track_id
            
            if best_track_id is not None:
                # Update existing track
                old_state = self.tracks[best_track_id]
                
                # Calculate velocity
                dt = timestamp - old_state.timestamp
                if dt > 0:
                    velocity = (np.array([
                        (det['bbox'][0][0] + det['bbox'][0][2]) / 2,
                        (det['bbox'][0][1] + det['bbox'][0][3]) / 2
                    ]) - old_state.center) / dt
                else:
                    velocity = old_state.velocity
                
                self.tracks[best_track_id] = ObjectState(
                    track_id=best_track_id,
                    label=det['label'],
                    bbox=det['bbox'][0],
                    confidence=det['confidence'],
                    timestamp=timestamp,
                    first_seen=old_state.first_seen,
                    frames_tracked=old_state.frames_tracked + 1,
                    velocity=velocity
                )
                
                self.ages[best_track_id] = 0
                matched_tracks.add(best_track_id)
                matched_detections.add(det_idx)
        
        # Create new tracks for unmatched detections
        for det_idx, det in enumerate(detections):
            if det_idx not in matched_detections:
                track_id = self.next_id
                self.next_id += 1
                
                self.tracks[track_id] = ObjectState(
                    track_id=track_id,
                    label=det['label'],
                    bbox=det['bbox'][0],
                    confidence=det['confidence'],
                    timestamp=timestamp,
                    frames_tracked=1
                )
                self.ages[track_id] = 0
        
        return self.tracks.copy()


class SpatialContextManager:
    """
    Advanced context manager with spatial-temporal tracking
    """
    
    def __init__(self, 
                 movement_threshold=30.0,  # pixels
                 time_threshold=10.0,      # seconds
                 max_history=20,
                 depth_estimator=None):
        
        self.tracker = IOUTracker()
        self.movement_threshold = movement_threshold
        self.time_threshold = time_threshold
        
        # Optional depth estimator for metric distance
        self.depth_estimator = depth_estimator
        self._last_depth_map = None
        
        # Memory structures
        self.active_objects: Dict[int, ObjectState] = {}
        self.last_announced: Dict[int, float] = defaultdict(float)
        self.last_positions: Dict[int, np.ndarray] = {}
        
        # Context history for LLM
        self.spatial_history = deque(maxlen=max_history)  # Recent spatial events
        self.scene_memory = deque(maxlen=5)  # Recent scene descriptions
        
        # Silence control
        self.silence_until = 0
        
    def set_silence_window(self, duration=5):
        """Block low-priority messages for 'duration' seconds"""
        self.silence_until = time.time() + duration
    
    def is_silenced(self):
        return time.time() < self.silence_until
    
    def _estimate_direction(self, center_x, frame_width=1280):
        """Estimate object direction based on position in frame"""
        third = frame_width / 3
        if center_x < third:
            return "left"
        elif center_x > 2 * third:
            return "right"
        else:
            return "center"
    
    def _estimate_distance(self, bbox_height, object_class, bbox=None):
        """Distance estimation using depth model (preferred) or bbox heuristic (fallback).
        
        If a depth estimator is available and has a cached depth map, uses per-pixel
        depth for accurate relative distance. Otherwise, falls back to the original
        bbox-height heuristic.
        """
        # Prefer depth-model based estimation
        if self.depth_estimator and self._last_depth_map is not None and bbox is not None:
            try:
                _, label = self.depth_estimator.get_object_distance(self._last_depth_map, bbox)
                return label
            except Exception:
                pass  # fall through to heuristic

        # Fallback: rough heuristic based on bbox size
        if bbox_height > 400:
            return "very close"
        elif bbox_height > 200:
            return "close"
        elif bbox_height > 100:
            return "medium distance"
        else:
            return "far"
    
    def update_depth_map(self, frame):
        """Run depth estimation on a frame and cache the result."""
        if self.depth_estimator and self.depth_estimator.is_ready:
            self._last_depth_map = self.depth_estimator.estimate(frame)
        return self._last_depth_map

    def update(self, detections: List[Dict], timestamp: float, frame_width=1280) -> List[Dict]:
        """
        Update spatial-temporal context with new detections
        
        Returns:
            List of spatial events to announce
        """
        # Update object tracking
        self.active_objects = self.tracker.update(detections, timestamp)
        
        events = []
        
        for track_id, obj in self.active_objects.items():
            # Update direction and distance estimates
            obj.direction = self._estimate_direction(obj.center[0], frame_width)
            obj.distance = self._estimate_distance(obj.bbox[3] - obj.bbox[1], obj.label, bbox=obj.bbox)
            
            # Check if this is a new object
            if track_id not in self.last_announced:
                event = {
                    "type": "NEW_OBJECT",
                    "track_id": track_id,
                    "label": obj.label,
                    "direction": obj.direction,
                    "distance": obj.distance,
                    "confidence": obj.confidence,
                    "timestamp": timestamp
                }
                events.append(event)
                self.last_announced[track_id] = timestamp
                self.last_positions[track_id] = obj.center.copy()
                
                # Add to spatial history
                self.spatial_history.append(
                    f"{obj.label} appeared {obj.direction} at {obj.distance} distance"
                )
                
            else:
                # Check if object moved significantly
                if track_id in self.last_positions:
                    movement = np.linalg.norm(obj.center - self.last_positions[track_id])
                    time_since_announce = timestamp - self.last_announced[track_id]
                    
                    if movement > self.movement_threshold and time_since_announce > self.time_threshold:
                        event = {
                            "type": "OBJECT_MOVED",
                            "track_id": track_id,
                            "label": obj.label,
                            "direction": obj.direction,
                            "distance": obj.distance,
                            "movement": movement,
                            "timestamp": timestamp
                        }
                        events.append(event)
                        self.last_announced[track_id] = timestamp
                        self.last_positions[track_id] = obj.center.copy()
                        
                        # Check if approaching (velocity toward camera)
                        if obj.velocity[1] > 10:  # Moving down in image = approaching
                            self.spatial_history.append(
                                f"{obj.label} is approaching from {obj.direction}"
                            )
        
        # Remove tracks for objects that disappeared
        disappeared_ids = set(self.last_announced.keys()) - set(self.active_objects.keys())
        for track_id in disappeared_ids:
            del self.last_announced[track_id]
            if track_id in self.last_positions:
                del self.last_positions[track_id]
        
        return events
    
    def add_scene_description(self, description: str):
        """Add VLM scene description to memory"""
        self.scene_memory.append({
            "description": description,
            "timestamp": time.time()
        })
    
    def get_context_for_llm(self) -> str:
        """
        Generate context string for LLM reasoning
        
        Returns formatted context including:
        - Currently tracked objects
        - Recent spatial events
        - Recent scene descriptions
        """
        context_parts = []
        
        # Current spatial state
        if self.active_objects:
            context_parts.append("=== CURRENT ENVIRONMENT ===")
            for obj in self.active_objects.values():
                context_parts.append(
                    f"- {obj.label}: {obj.direction} side, {obj.distance} "
                    f"(tracked for {obj.frames_tracked} frames)"
                )
        
        # Recent spatial events
        if self.spatial_history:
            context_parts.append("\n=== RECENT EVENTS ===")
            for event in list(self.spatial_history)[-5:]:  # Last 5 events
                context_parts.append(f"- {event}")
        
        # Recent scene descriptions
        if self.scene_memory:
            context_parts.append("\n=== SCENE UNDERSTANDING ===")
            for scene in list(self.scene_memory)[-2:]:  # Last 2 descriptions
                context_parts.append(f"- {scene['description']}")
        
        return "\n".join(context_parts) if context_parts else "No context available"
    
    def get_summary(self) -> str:
        """Get a brief summary of current state"""
        if not self.active_objects:
            return "No objects detected"
        
        summary_parts = []
        for obj in self.active_objects.values():
            summary_parts.append(f"{obj.label} {obj.direction}")
        
        return ", ".join(summary_parts)
