# safety/safety_rules.py

class SafetyRules:
    """
    Deterministic safety rules.
    No UI, no audio, no ML reasoning.
    """

    CRITICAL_OBJECTS = {
        "knife", "gun", "fire", "flame",
        "stairs", "hole", "open manhole",
        "car", "bus", "truck", "bike",
        "motorcycle", "train", "edge", "cliff"
    }

    WARNING_OBJECTS = {
         "crowd", "dog", "animal",
        "bicycle", "pole", "wall", "glass", "door"
    }

    INFO_OBJECTS = {
        "chair", "table", "bench", "bag", "box"
    }

    THRESHOLDS = {
        "CRITICAL_ALERT": 0.45,
        "WARNING": 0.50,
        "INFO": 0.60
    }

    def evaluate(self, detections):
        """
        Returns:
        ("CRITICAL_ALERT" | "WARNING" | "INFO", message)
        OR None
        """

        for d in detections:
            label = d["label"].lower()
            conf = d["confidence"]

            if label in self.CRITICAL_OBJECTS and conf >= self.THRESHOLDS["CRITICAL_ALERT"]:
                return (
                    "CRITICAL_ALERT",
                    f"Danger! {label} detected ahead. Stop immediately."
                )

            if label in self.WARNING_OBJECTS and conf >= self.THRESHOLDS["WARNING"]:
                return (
                    "WARNING",
                    f"Warning! {label} ahead. Proceed carefully."
                )

            if label in self.INFO_OBJECTS and conf >= self.THRESHOLDS["INFO"]:
                return (
                    "INFO",
                    f"{label} nearby."
                )

        return None
