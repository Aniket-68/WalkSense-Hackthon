# safety/frame_capture.py

import cv2

class Camera:
    def __init__(self, cam_id=None, width=None, height=None):
        from Infrastructure.config import Config
        
        # Determine source from Switch
        # We allow parameters to override the registry choice
        # Determine source from Switch
        # We allow parameters to override the registry choice
        source_type = Config.get("camera.mode", "hardware") if cam_id is None else "hardware"
        
        if source_type == "simulation" and cam_id is None:
            video_path = Config.get("camera.simulation.video_path")
            self.cap = cv2.VideoCapture(video_path)
            self.loop = Config.get("camera.simulation.loop", True)
            self.source_path = video_path
            print(f"[Camera] Simulation Mode: Reading from {video_path}")
        else:
            # Hardware mode
            c_id = cam_id if cam_id is not None else Config.get("camera.hardware.id", 0)
            c_w = width if width is not None else Config.get("camera.hardware.width", 1280)
            c_h = height if height is not None else Config.get("camera.hardware.height", 720)

            print(f"[Camera] Opening Hardware Device {c_id}...")
            # Use DirectShow on Windows for faster init, but fallback if needed
            self.cap = cv2.VideoCapture(c_id, cv2.CAP_DSHOW)
            
            # If failed to open or just weird result, try default backend
            if not self.cap.isOpened():
                print(f"[Camera] CAP_DSHOW failed. Trying default backend...")
                self.cap = cv2.VideoCapture(c_id)

            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, c_w)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, c_h)
            
            actual_w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            actual_h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            print(f"[Camera] Hardware Mode: Device {c_id} | Res: {int(actual_w)}x{int(actual_h)}")

        self.source_type = source_type

    def stream(self):
        while True:
            ret, frame = self.cap.read()
            if not ret:
                if hasattr(self, "loop") and self.loop:
                    # Restart video
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                break
            yield frame

    def release(self):
        self.cap.release()
