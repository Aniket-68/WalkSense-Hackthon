import cv2
import numpy as np

class SceneChangeDetector:
    def __init__(self, threshold=0.3):
        self.prev_hist = None
        self.threshold = threshold

    def has_changed(self, frame):
        """
        Returns True if the scene has changed significantly.
        Uses Histogram comparison for efficiency.
        """
        # Convert to HSV for better color lighting data (ignore V for lightness)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        
        # Calculate histogram (Hue and Saturation)
        hist = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)

        if self.prev_hist is None:
            self.prev_hist = hist
            return True # Always process the first frame

        # Compare with previous histogram
        # Correlation method: 1.0 is identical, 0.0 is different
        score = cv2.compareHist(self.prev_hist, hist, cv2.HISTCMP_CORREL)
        
        # Update previous
        self.prev_hist = hist
        
        # Logic: If correlation is High (> 0.9), scene is same. 
        # We return True if correlation is LOW (scene changed)
        # Using a strict threshold: 0.85 means "85% similar"
        # If score < 0.85, it means things changed enough to warrant a description.
        is_changed = score < (1.0 - self.threshold)
        
        if is_changed:
            print(f"[Scene] Changed (Score: {score:.2f})")
            
        return is_changed
