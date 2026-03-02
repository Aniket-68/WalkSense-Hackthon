# safety/yolo_detector.py
import torch
from ultralytics import YOLO
from Infrastructure.config import Config

class YoloDetector:
    def __init__(self, model_path=None):
        """
        Initializes the YOLO detector. 
        Loads model path and device settings from centralized config.json.
        """
        if model_path is None:
            active_model = Config.get("detector.active_model", "yolov8n")
            model_path = Config.get(f"detector.models.{active_model}", "models/yolo/yolov8n.pt")
        
        self.model = YOLO(model_path)
        
        # Determine device
        requested_device = Config.get("detector.device", "cpu")
        from loguru import logger
        if requested_device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA requested but not available. Falling back to CPU.")
            self.device = "cpu"
        else:
            self.device = requested_device
            
        logger.info(f"YOLO loading model on: {self.device}")
        self.model.to(self.device)
        self.conf_threshold = Config.get("detector.confidence_threshold", 0.25)

    def detect(self, frame):
        """
        Performs object detection on a frame.
        """
        results = self.model(frame, verbose=False, conf=self.conf_threshold)
        detections = []

        for r in results:
            for box in r.boxes:
                detections.append({
                    "label": self.model.names[int(box.cls)],
                    "confidence": float(box.conf),
                    "bbox": box.xyxy.tolist()
                })

        return detections
