# scripts/main.py
"""
Enhanced WalkSense demo with:
- Spatial-temporal object tracking
- LLM-based query answering
- Context-aware reasoning
"""

import sys
import os

# Add Inference folder to path for imports
inference_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, inference_root)

import cv2
import time

from Perception_Layer.camera import Camera
from Perception_Layer.detector import YoloDetector
from Perception_Layer.rules import SafetyRules

from Fusion_Layer.engine import FusionEngine
from Interaction_Layer.stt import ListeningLayer
from Interaction_Layer.tts import TTSEngine

from Reasoning_Layer.vlm import QwenVLM
from Infrastructure.sampler import FrameSampler
from Infrastructure.scene import SceneChangeDetector

# Optional depth estimation
try:
    from Perception_Layer.depth import DepthEstimator
    _DEPTH_AVAILABLE = True
except ImportError:
    _DEPTH_AVAILABLE = False

import threading
import queue
from loguru import logger
from Infrastructure.performance import tracker


# =========================================================
# VISUALIZATION (Same as before)
# =========================================================

def hazard_color(label: str) -> tuple[int, int, int]:
    """
    Returns a BGR color based on the object label for visualization.
    
    Args:
        label: The object label string.
        
    Returns:
        A tuple of (B, G, R) integers.
    """
    label = label.lower()
    if label in {"knife", "gun", "fire", "stairs", "car", "bus", "truck", "bike"}:
        return (0, 0, 255)  # Red for high danger
    if label in {"person", "dog", "animal", "bicycle", "wall", "glass"}:
        return (0, 255, 255)  # Yellow/Cyan for awareness
    if label in {"chair", "table", "bag"}:
        return (255, 0, 0)  # Blue for static objects
    return (0, 255, 0)  # Green for others


def draw_detections(frame, detections: list[dict]) -> object:
    """
    Draws bounding boxes and labels on the image frame.
    
    Args:
        frame: The OpenCV image frame (numpy array).
        detections: List of detection dictionaries containing 'bbox', 'label', and 'confidence'.
        
    Returns:
        The annotated image frame.
    """
    for d in detections:
        x1, y1, x2, y2 = map(int, d["bbox"][0])
        label = d["label"]
        conf = d["confidence"]
        color = hazard_color(label)
        
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        text = f"{label} {conf:.2f}"
        cv2.rectangle(frame, (x1, y1 - 22), (x1 + len(text) * 9, y1), color, -1)
        cv2.putText(frame, text, (x1 + 2, y1 - 5),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    return frame


def draw_overlay(frame, status: str, description: str, spatial_summary: str, vlm_ok: bool = False, llm_ok: bool = False, timeline: list = [], is_listening: bool = False, current_query: str = None, query_start_time: float = None) -> object:
    """
    Draws the UI overlay including status, spatial summary, and AI health indicators.
    
    Args:
        frame: The OpenCV image frame.
        status: Current system status string (e.g., 'RUNNING', 'PAUSED').
        description: Current scene description or alert message.
        spatial_summary: Summary of tracked objects in spatial context.
        vlm_ok: Health status of the VLM engine.
        llm_ok: Health status of the LLM engine.
        
    Returns:
        The image frame with overlay drawn.
    """
    h, w, _ = frame.shape
    import time
    t = time.time()
    
    # 1. TOP STATUS BAR (Glassmorphism effect)
    cv2.rectangle(frame, (0, 0), (w, 50), (15, 15, 15), -1)
    status_color = (0, 255, 0) if status == "RUNNING" else (0, 165, 255)
    if is_listening: status_color = (0, 255, 255) # Cyan for listening
    
    cv2.putText(frame, f"WALKSENSE OS // {status}", (20, 35),
               cv2.FONT_HERSHEY_DUPLEX, 0.7, status_color, 1)
    
    # 3. AI HEALTH (Right-aligned)
    vlm_c = (0, 255, 0) if vlm_ok else (0, 0, 255)
    cv2.circle(frame, (w-40, 25), 6, vlm_c, -1)
    cv2.putText(frame, "VLM", (w-85, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    llm_c = (0, 255, 0) if llm_ok else (0, 0, 255)
    cv2.circle(frame, (w-120, 25), 6, llm_c, -1)
    cv2.putText(frame, "LLM", (w-165, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    
    # 4. DIALOGUE TIMELINE (Left Floating Panel)
    if timeline:
        start_y = 120
        panel_h = len(timeline[-3:]) * 40 + 20
        overlay = frame.copy()
        cv2.rectangle(overlay, (15, start_y - 30), (int(w*0.45), start_y + panel_h - 30), (30, 30, 30), -1)
        cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)
        
        for entry in timeline[-3:]:
            prefix = entry.split(":")[0]
            color = (0, 255, 255) if "USER" in prefix else (100, 255, 100)
            cv2.circle(frame, (35, start_y - 5), 4, color, -1)
            cv2.putText(frame, entry, (50, start_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
            start_y += 40

    # 5. JARVIS CORE (Bottom Right)
    import math
    core_x, core_y = w - 100, h - 100
    pulse = (math.sin(t * 6) + 1) / 2
    inner_r = 15 + int(pulse * 10)
    outer_r = 35 + int(pulse * 5)
    
    core_color = (0, 255, 255) if is_listening else (255, 150, 0) 
    if "ALERT" in description.upper(): core_color = (0, 0, 255)
    
    cv2.circle(frame, (core_x, core_y), outer_r, core_color, 1)
    cv2.circle(frame, (core_x, core_y), inner_r, core_color, -1)
    
    angle = (t * 150) % 360
    cv2.ellipse(frame, (core_x, core_y), (45, 45), 0, angle, angle + 60, core_color, 2)
    cv2.ellipse(frame, (core_x, core_y), (45, 45), 0, angle + 180, angle + 240, core_color, 2)
    
    if is_listening:
        cv2.putText(frame, "LISTENING...", (w//2 - 100, h//2), cv2.FONT_HERSHEY_DUPLEX, 1.5, (0, 255, 255), 2)
        
    # NEW: Show Pending Query Prominently (Only if NOT currently answering)
    if current_query and "AI:" not in description:
        # Draw a highlight box
        qh, qw = 60, 800
        qx, qy = (w - qw)//2, h - 150
        
        # Glassmorphism background
        overlay = frame.copy()
        cv2.rectangle(overlay, (qx, qy), (qx + qw, qy + qh), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
        
        # Border
        cv2.rectangle(frame, (qx, qy), (qx + qw, qy + qh), (0, 255, 255), 1)
        
        # Text with latency indicator
        elapsed = time.time() - (query_start_time if query_start_time else time.time())
        cv2.putText(frame, f"QUERY: {current_query}", (qx + 20, qy + 40), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                   
        # Pulsing processing text
        if int(time.time() * 2) % 2 == 0:
            cv2.putText(frame, f"Processing... {elapsed:.1f}s", (qx + qw - 200, qy + 40),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)

    # 6. BOTTOM DESCRIPTION PANEL
    cv2.rectangle(frame, (0, h - 60), (w, h), (10, 10, 10), -1)
    
    # Use Green color if it's an AI response
    text_color = (100, 255, 100) if "AI:" in description else (255, 255, 255)
    
    cv2.putText(frame, f"WalkSense :: {description}", (20, h - 25),
               cv2.FONT_HERSHEY_SIMPLEX, 0.55, text_color, 1)
    
    cv2.putText(frame, f"SPATIAL SENSE: {spatial_summary}", (20, h - 45),
               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)
    
    return frame


# =========================================================
# ASYNC WORKER (Same as before)
# =========================================================

class QwenWorker:
    """
    Asynchronous worker for handling VLM scene description requests.
    Prevents blocking the main UI/capture thread during slow VLM inference.
    """
    def __init__(self, qwen_instance: object):
        """
        Initializes the worker with a QwenVLM instance.
        """
        self.qwen = qwen_instance
        self.input_queue = queue.Queue(maxsize=1)
        self.output_queue = queue.Queue()
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.is_busy = False
        
    def _run(self) -> None:
        """
        Internal worker loop that listens for input frames and triggers VLM inference.
        """
        while self.running:
            try:
                item = self.input_queue.get(timeout=0.1)
                frame, context_str = item
                
                self.is_busy = True
                try:
                    start = time.time()
                    desc = self.qwen.describe_scene(frame, context=context_str)
                    duration = time.time() - start
                    self.output_queue.put((desc, duration))
                except Exception as e:
                    print(f"[WORKER ERROR] {e}")
                finally:
                    self.is_busy = False
                    self.input_queue.task_done()
            except queue.Empty:
                continue
                
    def process(self, frame, context_str: str) -> bool:
        """
        Submits a frame and context for processing if the worker is not busy.
        
        Args:
            frame: The image frame to process.
            context_str: String containing detection labels and user query.
            
        Returns:
            True if the task was submitted, False if worker was busy or queue full.
        """
        if not self.is_busy and self.input_queue.empty():
            self.input_queue.put((frame.copy(), context_str))
            return True
        return False
        
    def get_result(self) -> tuple[str, float] | None:
        """
        Retrieves the latest result from the output queue if available.
        
        Returns:
            A tuple containing (description, duration) or None if no result is ready.
        """
        try:
            return self.output_queue.get_nowait()
        except queue.Empty:
            return None
            
    def stop(self) -> None:
        """
        Signals the worker thread to stop.
        """
        self.running = False


# =========================================================
# MAIN
# =========================================================

def main() -> None:
    """
    Main execution loop for WalkSense Enhanced.
    Initializes hardware, model engines, and enters the real-time processing loop.
    """
    # Load central configuration
    from Infrastructure.config import Config
    
    # 🟢 Camera Configuration
    CAMERA_SOURCE = Config.get("camera.source", 0)
    
    # 🟢 VLM Configuration
    VLM_PROVIDER = Config.get("vlm.active_provider", "lm_studio")
    vlm_config_path = f"vlm.providers.{VLM_PROVIDER}"
    VLM_URL = Config.get(f"{vlm_config_path}.url")
    # For local provider, resolve model_id from active_model → models dict
    if VLM_PROVIDER in ("local", "huggingface_api"):
        _vlm_active = Config.get(f"{vlm_config_path}.active_model")
        VLM_MODEL = Config.get(f"{vlm_config_path}.models.{_vlm_active}.model_id") if _vlm_active else Config.get(f"{vlm_config_path}.model_id")
    else:
        VLM_MODEL = Config.get(f"{vlm_config_path}.model_id")
    
    # 🟢 LLM Configuration
    LLM_PROVIDER = Config.get("llm.active_provider", "ollama")
    llm_config_path = f"llm.providers.{LLM_PROVIDER}"
    LLM_URL = Config.get(f"{llm_config_path}.url")
    # For local provider, resolve model_id from active_model → models dict
    if LLM_PROVIDER in ("local", "huggingface_api"):
        _llm_active = Config.get(f"{llm_config_path}.active_model")
        LLM_MODEL = Config.get(f"{llm_config_path}.models.{_llm_active}.model_id") if _llm_active else Config.get(f"{llm_config_path}.model_id")
    else:
        LLM_MODEL = Config.get(f"{llm_config_path}.model_id")
    
    # 🟢 TTS Configuration handled internally in audio/speak.py via config.json
    
    # 🟢 Perception Thresholds
    SAMPLING = Config.get("perception.sampling_interval", 150)
    SCENE_THRESH = Config.get("perception.scene_threshold", 0.15)
    WINDOW_WIDTH = Config.get("camera.hardware.width", 1280)
    WINDOW_HEIGHT = Config.get("camera.hardware.height", 720)
    
    camera = Camera()
    detector = YoloDetector()
    safety = SafetyRules()
    
    tts = TTSEngine()
    
    # 🟣 Depth Estimation (optional)
    depth = None
    if _DEPTH_AVAILABLE and Config.get("depth.enabled", False):
        try:
            depth = DepthEstimator()
            if depth.is_ready:
                logger.info("Depth Estimator loaded successfully")
            else:
                logger.warning("Depth Estimator failed to load — using bbox heuristic")
                depth = None
        except Exception as e:
            logger.warning(f"Depth init failed: {e} — using bbox heuristic")
            depth = None
    else:
        logger.info("Depth estimation disabled or unavailable")
    
    # Enhanced Fusion Engine with LLM
    logger.info("Creating Enhanced Fusion Engine...")
    fusion = FusionEngine(
        tts, 
        llm_backend=LLM_PROVIDER, 
        llm_url=LLM_URL,
        llm_model=LLM_MODEL,
        depth_estimator=depth
    )
    
    # Interaction Layer
    listener = ListeningLayer(None, fusion)
    
    logger.info("Loading Qwen VLM...")
    qwen = QwenVLM(
        backend=VLM_PROVIDER,
        model_id=VLM_MODEL,
        lm_studio_url=VLM_URL
    )
    
    sampler = FrameSampler(every_n_frames=SAMPLING)
    scene_detector = SceneChangeDetector(threshold=SCENE_THRESH)
    qwen_worker = QwenWorker(qwen)
    
    # UI Variables
    started = False
    description = "System idle. Press S to start."
    current_user_query = None
    llm_response = ""
    llm_response_timer = 0
    llm_response_timer = 0
    is_listening = False
    query_start_time = None
    dialogue_history = []  # Stores last few interactions

    cv2.namedWindow("WalkSense Enhanced", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("WalkSense Enhanced", WINDOW_WIDTH, WINDOW_HEIGHT)
    

    # Threaded Listener Wrapper
    def threaded_listen() -> None:
        """
        Runs the speech-to-text listener in a separate thread to avoid UI lag.
        Updates shared 'current_user_query' upon successful recognition.
        """
        nonlocal current_user_query, is_listening, llm_response, llm_response_timer, query_start_time
        is_listening = True
        # 🔴 STOP TTS IMMEDIATELY to prevent interference
        tts.stop()
        
        max_retries = 2
        for attempt in range(max_retries):
            # PROMPT USER
            if attempt == 0:
                tts.speak("What do you want to know?")
            else:
                tts.speak("I didn't hear you. What do you want to know?")
                
            update_status("ASKING...")
            time.sleep(1.8) # Wait for TTS to finish roughly
            
            logger.info(f"Listening thread started (Attempt {attempt+1})...")
            tracker.start_timer("stt")
            query = listener.stt.listen_once()
            tracker.stop_timer("stt")
            
            if query:
                print(f"\n[USER QUERY] >>> {query} <<<\n")
                logger.info(f"USER: {query}")
                current_user_query = query
                query_start_time = time.time()
                dialogue_history.append(f"USER: {query}")
                
                # Get immediate answer (Stage 1)
                immediate_ans = fusion.handle_user_query(query)
                if immediate_ans:
                    llm_response = f"AI: {immediate_ans}"
                    llm_response_timer = time.time() + 10
                    dialogue_history.append(f"AI: {immediate_ans}")
                break # Success
            
            # If query is None (Timeout), loop continues
        
        is_listening = False
    
    # Helper to update status in the thread if needed (requires thread safety but variables are simple)
    def update_status(msg):
        nonlocal description
        # description = msg # Optional: don't override scene desc
        pass

    for frame in camera.stream():
        current_time = time.time()
        tracker.start_timer("frame_total")
        
        # YOLO Detection
        tracker.start_timer("yolo")
        detections = detector.detect(frame)
        tracker.stop_timer("yolo")
        
        # Keep clean frame for VLM/Scene detection
        clean_frame = frame.copy()
        
        frame = draw_detections(frame, detections)
        
        # 🔴 SAFETY LAYER
        safety_result = safety.evaluate(detections)
        if safety_result:
            alert_type, message = safety_result
            logger.warning(f"Safety Alert: {message}")
            fusion.handle_safety_alert(message, alert_type)
            description = f"ALERT: {message}"
        
        # 🟢 SPATIAL TRACKING
        if started:
            fusion.update_spatial_context(detections, current_time, frame.shape[1], frame=clean_frame)
        
        # 🟡 VLM & LLM PROCESSING
        is_critical = safety_result and safety_result[0] == "CRITICAL_ALERT"
        
        if started and not is_critical:
            # 1. Harvest Results
            result = qwen_worker.get_result()
            if result:
                new_desc, duration = result
                logger.info(f"VLM Description: {new_desc}")
                description = new_desc
                
                if current_user_query:
                    tracker.start_timer("llm_reasoning")
                    answer = fusion.handle_vlm_description(new_desc)
                    tracker.stop_timer("llm_reasoning")
                    if answer:
                        llm_response = f"AI: {answer}"
                        llm_response_timer = time.time() + 10 # Show for 10s
                        dialogue_history.append(f"AI: {answer}")
                        logger.info(f"LLM Answer: {answer}")
                        
                        # TTS is already handled by the router when routing the RESPONSE event
                        # No need to call tts.speak() here as it would be redundant
                        
                        current_user_query = None
                else:
                    fusion.handle_scene_description(new_desc)
                    logger.info("VLM Update (Silent)")
            
            # 2. Trigger Logic
            has_query = (current_user_query is not None)
            time_to_sample = sampler.should_sample()
            should_run_qwen = False
            
            if has_query:
                should_run_qwen = True # Priority
            elif time_to_sample and scene_detector.has_changed(clean_frame):
                should_run_qwen = True
            
            if should_run_qwen:
                context_str = ", ".join([d["label"] for d in detections])
                if has_query:
                    context_str += f". USER QUESTION: {current_user_query}"
                
                # Send to worker (non-blocking)
                if qwen_worker.process(clean_frame, context_str):
                    status_text = "Reasoning..." if has_query else "Scanning..."
                    cv2.putText(frame, status_text, (frame.shape[1]-150, 60),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        # UI Overlay Construction
        status = "RUNNING" if started else "PAUSED"
        if is_listening: status = "LISTENING..."
        
        # Check if we are in the 'prompting' phase (heuristically, if is_listening but mic not open yet/during sleep)
        # Actually, let's just rely on LISTENING... for now, or add a shared variable.
        # But for simplicity, let the user see 'LISTENING...' while the AI asks. 
        # It serves as a 'Attention' signal.
        
        vlm_ok = True
        llm_ok = (sampler.counter % 30 != 0) or fusion.llm.check_health()
        
        # Override description with LLM response if active
        display_text = description
        if time.time() < llm_response_timer and llm_response:
             display_text = llm_response

        spatial_summary = fusion.get_spatial_summary()
        frame = draw_overlay(
            frame, status, display_text, spatial_summary, 
            vlm_ok, llm_ok, 
            timeline=dialogue_history,
            is_listening=is_listening,
            current_query=current_user_query,
            query_start_time=query_start_time
        )
        
        tracker.stop_timer("frame_total")
        
        # Occasional Performance Print
        if sampler.counter % 100 == 0 and sampler.counter > 0:
            logger.info(f"Performance Stats: {tracker.get_summary()}")
        
        cv2.imshow("WalkSense Enhanced", frame)
        key = cv2.waitKey(1) & 0xFF
        
        # --- CONTROLS ---
        if key in (ord('s'), ord('S')):
            started = not started
            state = "Started" if started else "Paused"
            logger.info(f"System {state}")
            tts.speak(f"System {state}")

        elif key in (ord('l'), ord('L')):
            if not is_listening:
                threading.Thread(target=threaded_listen, daemon=True).start()

        elif key in (ord('k'), ord('K')):
            # HARDCODED TEST QUERY
            logger.info("Injecting Hardcoded Query...")
            current_user_query = "What obstacles are in front of me?"
            fusion.handle_user_query(current_user_query)
            tts.speak("Analyzing obstacles")

        elif key in (ord('m'), ord('M')):
            is_muted = fusion.router.toggle_mute()
            logger.info(f"Muted: {is_muted}")

        elif key in (ord('q'), ord('Q')):
            logger.info("Quitting system...")
            tracker.plot_metrics()
            break
    
    qwen_worker.stop()
    camera.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
