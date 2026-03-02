# scripts/download_yolo.py
import os
from ultralytics import YOLO
import shutil

def download_yolo_model(model_name="yolo11m.pt", target_dir="models/yolo"):
    """
    Downloads a YOLO model weights file and moves it to the target directory.
    """
    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)
        
    target_path = os.path.join(target_dir, model_name)
    
    if os.path.exists(target_path):
        print(f"[SKIP] {model_name} already exists in {target_dir}")
        return True
    
    print(f"[INFO] Downloading {model_name}...")
    try:
        # Ultralytics downloads to current dir by default
        model = YOLO(model_name)
        
        # Move it to the target directory
        if os.path.exists(model_name):
            shutil.move(model_name, target_path)
            print(f"[OK] {model_name} downloaded and moved to {target_path}")
            return True
        else:
            print(f"[ERROR] {model_name} download failed (file not found after download attempt)")
            return False
            
    except Exception as e:
        print(f"[ERROR] Failed to download {model_name}: {e}")
        return False

if __name__ == "__main__":
    download_yolo_model("yolo11m.pt")
    download_yolo_model("yolov8n.pt")
