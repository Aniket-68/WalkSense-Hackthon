"""
SystemManager: Thread-safe singleton that owns the WalkSense processing pipeline.
Replaces the OpenCV main loop from run_enhanced_camera.py with a headless server-side loop.
"""

import sys
import os

# Add Inference folder to path for imports
backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
inference_path = os.path.join(backend_root, 'Inference')
sys.path.insert(0, inference_path)

import cv2
import time
import threading
import queue
from collections import deque
from typing import Optional, Dict, Any, List
from loguru import logger
from dataclasses import dataclass, field


class SystemManager:
    """Central manager for the WalkSense processing pipeline.
    
    Runs the camera → YOLO → safety → VLM → LLM pipeline in a background thread
    and exposes state via get_state() for the WebSocket API.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # State
        self._running = False
        self._system_status = "IDLE"
        self._loop_thread: Optional[threading.Thread] = None
        self._start_thread: Optional[threading.Thread] = None
        self._lifecycle_lock = threading.Lock()
        self._run_generation = 0

        # Pipeline component states
        self._pipeline_state = {
            "camera":  {"active": False, "last_latency_ms": 0},
            "yolo":    {"active": False, "detections_count": 0, "last_latency_ms": 0},
            "safety":  {"active": False, "last_alert": None},
            "vlm":     {"active": False, "is_processing": False, "last_latency_ms": 0},
            "llm":     {"active": False, "is_processing": False, "last_latency_ms": 0},
            "tts":     {"active": False, "is_speaking": False},
            "stt":     {"active": False, "is_listening": False},
        }

        # Data
        self._latest_description = ""
        self._spatial_summary = ""
        self._current_query: Optional[str] = None
        self._current_response: Optional[str] = None
        self._dialogue_history = deque(maxlen=int(os.getenv("SYSTEM_DIALOGUE_HISTORY_MAX", "200")))
        self._history_lock = threading.Lock()
        self._detections: list = []

        # Frame buffer
        self._frame_lock = threading.Lock()
        self._latest_frame: Optional[bytes] = None  # JPEG bytes
        self._latest_raw_frame = None  # numpy array for VLM

        # Browser camera frame queue (for camera.mode = "browser")
        self._browser_frame_queue: queue.Queue = queue.Queue(maxsize=2)
        # Read camera mode early so get_state() reports correctly before start
        from Infrastructure.config import Config
        self._camera_mode = Config.get("camera.mode", "hardware")

        # Remote TTS state (sent to clients via WebSocket)
        self._tts_remote_mode = Config.get("tts.remote_mode", "browser")
        self._tts_seq: int = 0          # monotonically increasing; client deduplicates
        # Sliding window of recent utterances — NOT drained on read.
        # Each item: {"text", "seq", "priority", "ts"}
        # Items older than _TTS_WINDOW_SECS are pruned on append.
        self._tts_buffer: list = []
        self._tts_lock = threading.Lock()
        _TTS_WINDOW_SECS = 10  # keep utterances for 10s so late-joining clients catch up
        self._tts_window = _TTS_WINDOW_SECS
        # Audio bytes queue for server-side TTS streaming (/ws/audio)
        self._audio_queue: queue.Queue = queue.Queue(maxsize=8)

        # Query queue
        self._query_queue: queue.Queue = queue.Queue(maxsize=int(os.getenv("SYSTEM_QUERY_QUEUE_MAXSIZE", "64")))

        # Lazy-loaded components (initialized on start)
        self._camera = None
        self._detector = None
        self._safety = None
        self._tts = None
        self._fusion = None
        self._qwen = None
        self._sampler = None
        self._scene_detector = None
        self._qwen_worker = None
        self._llm_worker = None
        self._muted = False

        logger.info("[SystemManager] Initialized (singleton)")

    def _init_components(self):
        """Lazy-initialize all pipeline components."""
        import os
        from Infrastructure.config import Config
        from Perception_Layer.camera import Camera
        from Perception_Layer.detector import YoloDetector
        from Perception_Layer.rules import SafetyRules
        from Fusion_Layer.engine import FusionEngine
        from Interaction_Layer.tts import TTSEngine
        from Reasoning_Layer.vlm import QwenVLM
        from Infrastructure.sampler import FrameSampler
        from Infrastructure.scene import SceneChangeDetector

        # Optional depth estimation
        _depth_available = False
        try:
            from Perception_Layer.depth import DepthEstimator
            _depth_available = True
        except ImportError:
            pass

        # VLM config
        vlm_provider = Config.get("vlm.active_provider", "lm_studio")
        vlm_config_path = f"vlm.providers.{vlm_provider}"
        vlm_url = Config.get(f"{vlm_config_path}.url")
        # For local/huggingface_api, resolve model_id from active_model → models dict
        if vlm_provider in ("local", "huggingface_api"):
            _vlm_active = Config.get(f"{vlm_config_path}.active_model")
            vlm_model = Config.get(f"{vlm_config_path}.models.{_vlm_active}.model_id") if _vlm_active else Config.get(f"{vlm_config_path}.model_id")
        else:
            vlm_model = Config.get(f"{vlm_config_path}.model_id")
        vlm_api_key = None
        if vlm_provider == "gemini":
            vlm_api_env = Config.get(f"{vlm_config_path}.api_key_env", "GEMINI_API_KEY")
            vlm_api_key = os.getenv(vlm_api_env)
            if not vlm_api_key:
                logger.warning(f"[SystemManager] Gemini VLM API key not found in env var: {vlm_api_env}")

        # LLM config
        llm_provider = Config.get("llm.active_provider", "ollama")
        llm_config_path = f"llm.providers.{llm_provider}"
        llm_url = Config.get(f"{llm_config_path}.url", "")
        # For local/huggingface_api, resolve model_id from active_model → models dict
        if llm_provider in ("local", "huggingface_api"):
            _llm_active = Config.get(f"{llm_config_path}.active_model")
            llm_model = Config.get(f"{llm_config_path}.models.{_llm_active}.model_id") if _llm_active else Config.get(f"{llm_config_path}.model_id")
        else:
            llm_model = Config.get(f"{llm_config_path}.model_id")
        
        # API key for Gemini (read from env var specified in config)
        llm_api_key = None
        if llm_provider == "gemini":
            api_key_env = Config.get(f"{llm_config_path}.api_key_env", "GEMINI_API_KEY")
            llm_api_key = os.getenv(api_key_env)
            if not llm_api_key:
                logger.warning(f"[SystemManager] Gemini API key not found in env var: {api_key_env}")

        # Perception thresholds
        sampling = Config.get("perception.sampling_interval", 150)
        scene_thresh = Config.get("perception.scene_threshold", 0.15)

        # Camera mode: "hardware", "simulation", or "browser"
        self._camera_mode = Config.get("camera.mode", "hardware")
        logger.info(f"[SystemManager] Camera mode: {self._camera_mode}")

        logger.info("[SystemManager] Initializing pipeline components...")

        # Only create Camera for hardware/simulation modes — browser frames come via WebSocket
        if self._camera_mode != "browser":
            self._camera = Camera()
        else:
            self._camera = None
            logger.info("[SystemManager] Browser camera mode — frames received via /ws/camera")

        self._detector = YoloDetector()
        self._safety = SafetyRules()
        self._tts = TTSEngine()

        # Depth estimation (optional)
        self._depth = None
        if _depth_available and Config.get("depth.enabled", False):
            try:
                self._depth = DepthEstimator()
                if self._depth.is_ready:
                    logger.info("[SystemManager] Depth Estimator loaded successfully")
                else:
                    logger.warning("[SystemManager] Depth Estimator failed — using bbox heuristic")
                    self._depth = None
            except Exception as e:
                logger.warning(f"[SystemManager] Depth init failed: {e} — using bbox heuristic")
                self._depth = None
        else:
            logger.info("[SystemManager] Depth estimation disabled or unavailable")

        self._fusion = FusionEngine(
            self._tts,
            llm_backend=llm_provider,
            llm_url=llm_url,
            llm_model=llm_model,
            llm_api_key=llm_api_key,
            depth_estimator=self._depth
        )

        # Wire remote TTS callback so router can emit to clients
        self._fusion.router.set_remote_tts(self.emit_tts)

        self._qwen = QwenVLM(
            backend=vlm_provider,
            model_id=vlm_model,
            lm_studio_url=vlm_url,
            api_key=vlm_api_key,
        )

        self._sampler = FrameSampler(every_n_frames=sampling)
        self._scene_detector = SceneChangeDetector(threshold=scene_thresh)

        # VLM worker (async VLM inference in background thread)
        self._qwen_worker = _QwenWorker(self._qwen)

        # LLM worker (async LLM inference in background thread)
        self._llm_worker = _LLMWorker(self._fusion)

        # Pre-load Whisper STT model
        self._preload_whisper(Config)

        logger.info("[SystemManager] All components initialized")

    def _preload_whisper(self, Config):
        """Pre-load Whisper model during startup to avoid lag on first voice query."""
        import os
        try:
            provider = Config.get("stt.active_provider", "local")
            if provider == "deepgram":
                # Remote STT provider, no local model preload required
                self._whisper_model = None
                self._whisper_backend = "deepgram"
                logger.info("[STT] Deepgram provider selected — skipping local Whisper preload")
                return

            if provider != "local":
                # Other remote providers are not currently wired for /api/voice-query
                self._whisper_model = None
                self._whisper_backend = provider
                logger.info(f"[STT] Provider '{provider}' selected — no local preload")
                return

            config_path = f"stt.providers.{provider}"
            # Resolve model_size from nested active_model → models dict
            _active = Config.get(f"{config_path}.active_model")
            model_size = Config.get(f"{config_path}.models.{_active}.model_size", "small") if _active else Config.get(f"{config_path}.model_size", "small")
            device = Config.get(f"{config_path}.device", "cuda")
            compute_type = Config.get(f"{config_path}.compute_type", "int8")

            project_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Inference")
            model_dir = os.path.join(project_root, "Models", "stt")

            logger.info(f"[STT] Pre-loading Whisper model '{model_size}' on {device}...")
            
            # ENFORCE GPU - No CPU fallback
            if device == "cuda":
                try:
                    from faster_whisper import WhisperModel
                    self._whisper_model = WhisperModel(
                        model_size, device=device, compute_type=compute_type,
                        download_root=model_dir
                    )
                    self._whisper_backend = "faster_whisper"
                    logger.info(f"[STT] ✓ Faster-Whisper loaded successfully on CUDA ({model_size})")
                    return
                except Exception as e:
                    logger.error(f"[STT] ✗ CUDA REQUIRED but failed: {e}")
                    logger.error("[STT] ═══════════════════════════════════════")
                    logger.error("[STT] GPU ENFORCEMENT: Install CUDA PyTorch:")
                    logger.error("[STT] pip uninstall torch torchvision torchaudio")  
                    logger.error("[STT] pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")
                    logger.error("[STT] ═══════════════════════════════════════")
                    raise RuntimeError(f"CUDA required but unavailable: {e}")

            # CPU only allowed if explicitly configured
            elif device == "cpu":
                from faster_whisper import WhisperModel
                self._whisper_model = WhisperModel(
                    model_size, device="cpu", compute_type="int8",
                    download_root=model_dir
                )
                self._whisper_backend = "faster_whisper"
                logger.info(f"[STT] Faster-Whisper loaded on CPU ({model_size}) - GPU disabled by config")
            else:
                raise ValueError(f"Invalid device: {device}")
                
        except Exception as e:
            logger.error(f"[STT] Pre-load failed: {e}")
            self._whisper_model = None
            self._whisper_backend = None
            raise  # Re-raise to stop initialization

    def _transcribe_deepgram(self, audio_bytes: bytes) -> Optional[str]:
        """Transcribe audio via Deepgram REST API."""
        import requests

        from Infrastructure.config import Config
        config_path = "stt.providers.deepgram"

        api_key_env = Config.get(f"{config_path}.api_key_env", "DEEPGRAM_API_KEY")
        api_key = os.getenv(api_key_env)
        if not api_key:
            logger.error(f"[STT] Deepgram API key missing in env var: {api_key_env}")
            return None

        api_url = Config.get(f"{config_path}.url", "https://api.deepgram.com/v1/listen")
        model_id = Config.get(f"{config_path}.model_id", "nova-3")
        language = Config.get(f"{config_path}.language", "multi")
        timeout_s = Config.get(f"{config_path}.timeout", 20)
        content_type = Config.get(f"{config_path}.content_type", "audio/wav")

        params = {
            "model": model_id,
            "language": language,
            "smart_format": str(bool(Config.get(f"{config_path}.smart_format", True))).lower(),
            "punctuate": str(bool(Config.get(f"{config_path}.punctuate", True))).lower(),
        }

        headers = {
            "Authorization": f"Token {api_key}",
            "Content-Type": content_type,
        }

        try:
            start = time.time()
            response = requests.post(
                api_url,
                params=params,
                headers=headers,
                data=audio_bytes,
                timeout=timeout_s,
            )
            response.raise_for_status()
            payload = response.json()

            transcript = (
                payload.get("results", {})
                .get("channels", [{}])[0]
                .get("alternatives", [{}])[0]
                .get("transcript", "")
                .strip()
            )

            duration = (time.time() - start) * 1000
            if transcript:
                logger.info(f"[STT] Deepgram transcribed in {duration:.0f}ms: {transcript}")
                return transcript

            logger.info(f"[STT] Deepgram returned empty transcript in {duration:.0f}ms")
            return None
        except Exception as e:
            logger.error(f"[STT] Deepgram transcription failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Start the processing pipeline."""
        with self._lifecycle_lock:
            if self._running or self._system_status == "STARTING":
                return
            self._system_status = "STARTING"
            self._run_generation += 1
            generation = self._run_generation
            logger.info("[SystemManager] System starting — loading components...")

            # Run heavy init in a thread so the API responds immediately
            self._start_thread = threading.Thread(
                target=self._start_async,
                args=(generation,),
                daemon=True,
            )
            self._start_thread.start()

    def _start_async(self, generation: int):
        """Background thread that loads components then starts the pipeline."""
        try:
            # Re-init if components were never loaded, or if camera was
            # released after a previous stop (the finally block in
            # _main_loop sets self._camera = None).
            needs_init = (
                self._detector is None
                or self._qwen_worker is None
                or not self._qwen_worker.running
                or self._llm_worker is None
                or not self._llm_worker.running
                or (self._camera is None and self._camera_mode != "browser")
            )
            if needs_init:
                self._init_components()

            with self._lifecycle_lock:
                if generation != self._run_generation or self._system_status != "STARTING":
                    logger.info("[SystemManager] Start request superseded; aborting startup.")
                    return
                self._running = True
                self._system_status = "RUNNING"
                self._loop_thread = threading.Thread(
                    target=self._main_loop,
                    args=(generation,),
                    daemon=True,
                )
                self._loop_thread.start()
            logger.info("[SystemManager] Pipeline started")
        except Exception as e:
            logger.error(f"[SystemManager] Failed to start: {e}")
            import traceback
            traceback.print_exc()
            with self._lifecycle_lock:
                if generation == self._run_generation:
                    self._system_status = "ERROR"
                    self._running = False
        finally:
            with self._lifecycle_lock:
                self._start_thread = None

    def stop(self):
        """Stop the processing pipeline."""
        with self._lifecycle_lock:
            self._run_generation += 1
            self._running = False
            if self._system_status != "IDLE":
                self._system_status = "STOPPING"

            loop_thread = self._loop_thread
            start_thread = self._start_thread
            self._loop_thread = None
            self._start_thread = None
            qwen_worker = self._qwen_worker
            llm_worker = self._llm_worker

        if qwen_worker:
            qwen_worker.stop()
        if llm_worker:
            llm_worker.stop()

        if loop_thread and loop_thread.is_alive():
            loop_thread.join(timeout=5)
        if start_thread and start_thread.is_alive():
            start_thread.join(timeout=5)

        # Reset pipeline states
        for key in self._pipeline_state:
            self._pipeline_state[key]["active"] = False
            if "is_processing" in self._pipeline_state[key]:
                self._pipeline_state[key]["is_processing"] = False

        self._system_status = "IDLE"
        logger.info("[SystemManager] Pipeline stopped")

    def submit_query(self, text: str):
        """Submit a user text query."""
        try:
            self._query_queue.put_nowait(text)
        except queue.Full:
            try:
                # Drop oldest query to keep queue bounded and non-blocking.
                self._query_queue.get_nowait()
            except queue.Empty:
                pass
            self._query_queue.put_nowait(text)
            logger.warning("[SystemManager] Query queue full; dropped oldest pending query")
        self._current_query = text
        self._pipeline_state["stt"]["active"] = True
        with self._history_lock:
            self._dialogue_history.append({
                "role": "user",
                "text": text,
                "timestamp": time.time()
            })
        logger.info(f"[SystemManager] Query submitted: {text}")

    def toggle_mute(self) -> bool:
        """Toggle audio mute."""
        if self._fusion:
            self._muted = self._fusion.router.toggle_mute()
        return self._muted

    def transcribe_audio(self, audio_bytes: bytes) -> Optional[str]:
        """Transcribe WAV audio bytes using the configured STT provider."""
        import tempfile
        import os
        from Infrastructure.config import Config

        provider = Config.get("stt.active_provider", "local")
        if provider == "deepgram":
            return self._transcribe_deepgram(audio_bytes)

        if provider != "local":
            logger.error(f"[STT] Unsupported provider for /api/voice-query: {provider}")
            return None

        if not getattr(self, '_whisper_model', None):
            logger.error("[STT] Whisper model not loaded")
            return None

        try:
            language = Config.get(f"stt.providers.{provider}.language", "en")

            logger.debug(f"[STT] Starting transcription: backend={self._whisper_backend}, language={language}")

            # Save audio bytes to temp file for transcription
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_bytes)
                temp_path = f.name

            try:
                start = time.time()
                logger.debug(f"[STT] Calling transcribe on temp file: {temp_path}")
                
                if self._whisper_backend == "faster_whisper":
                    logger.debug("[STT] Using faster-whisper backend")
                    segments, info = self._whisper_model.transcribe(
                        temp_path,
                        language=language,
                        vad_filter=False,           # Disable VAD — it clips short utterances
                        no_speech_threshold=0.4,    # Lower threshold to keep faint speech
                        condition_on_previous_text=False,  # Prevent hallucination carry-over
                    )
                    text = " ".join([seg.text for seg in segments]).strip()
                    logger.debug(f"[STT] faster-whisper completed, detected language: {info.language}")
                elif "openai" in self._whisper_backend:
                    logger.debug("[STT] Using openai-whisper backend")
                    result = self._whisper_model.transcribe(temp_path, language=language, fp16=False)
                    text = result["text"].strip() if isinstance(result, dict) else str(result).strip()
                    logger.debug("[STT] openai-whisper completed")
                else:
                    logger.error(f"[STT] Unknown backend: {self._whisper_backend}")
                    return None

                duration = (time.time() - start) * 1000
                logger.info(f"[STT] Transcribed in {duration:.0f}ms: {text}")
                return text if text else None
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

        except Exception as e:
            logger.error(f"[STT] Transcription failed: {e}")
            import traceback
            logger.error(f"[STT] Full traceback: {traceback.format_exc()}")
            
            # NO CPU FALLBACK - Enforce GPU usage
            if "cublas" in str(e) or "cuda" in str(e).lower():
                logger.error("[STT] ═══════════════════════════════════════")
                logger.error("[STT] CUDA ERROR - Install proper PyTorch:")
                logger.error("[STT] pip uninstall torch torchvision torchaudio")
                logger.error("[STT] pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")
                logger.error("[STT] ═══════════════════════════════════════")
            return None

    # ------------------------------------------------------------------
    # State API
    # ------------------------------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        """Get the full system state for WebSocket broadcast."""
        # Snapshot recent TTS utterances (NOT drained — all clients see them;
        # frontend deduplicates via lastSeq).
        with self._tts_lock:
            tts_queue = [{"text": u["text"], "seq": u["seq"], "priority": u["priority"]}
                         for u in self._tts_buffer]
        with self._history_lock:
            dialogue_history = list(self._dialogue_history)[-20:]

        return {
            "system_status": self._system_status,
            "camera_mode": self._camera_mode or "hardware",
            "tts_remote_mode": self._tts_remote_mode,
            "tts_queue": tts_queue,    # list of {"text", "seq", "priority"}
            "pipeline": {k: dict(v) for k, v in self._pipeline_state.items()},
            "latest_description": self._latest_description,
            "spatial_summary": self._spatial_summary,
            "current_query": self._current_query,
            "current_response": self._current_response,
            "dialogue_history": dialogue_history,  # last 20
            "muted": self._muted,
        }

    # ------------------------------------------------------------------
    # Remote TTS helpers
    # ------------------------------------------------------------------

    def emit_tts(self, text: str, priority: str = "response"):
        """Emit TTS text for remote clients.

        Depending on ``tts.remote_mode`` in config.json:
        - "browser"  → text sent via WebSocket state; client uses Web Speech API
        - "server"   → audio synthesized here and queued for /ws/audio streaming
        - "hybrid"   → critical/warning via browser, response/scene via server audio
        - "local"    → only plays on server speakers (legacy)
        """
        if not text:
            return

        mode = self._tts_remote_mode

        # Append to sliding-window buffer; prune old entries.
        self._tts_seq += 1
        now = time.time()
        with self._tts_lock:
            self._tts_buffer.append({
                "text": text,
                "seq": self._tts_seq,
                "priority": priority,
                "ts": now,
            })
            # Prune utterances older than the window
            cutoff = now - self._tts_window
            self._tts_buffer = [u for u in self._tts_buffer if u["ts"] >= cutoff]

        use_browser = False
        use_server_audio = False
        use_local = False

        if mode == "browser":
            use_browser = True
        elif mode == "server":
            use_server_audio = True
        elif mode == "hybrid":
            # Fast browser TTS for safety-critical, server audio for longer responses
            if priority in ("critical", "warning"):
                use_browser = True
            else:
                use_server_audio = True
        elif mode == "local":
            use_local = True
        else:
            use_browser = True  # safe default

        # Server-side audio synthesis → queue bytes for /ws/audio
        if use_server_audio and self._tts:
            try:
                audio_bytes = self._tts.synthesize_to_bytes(text)
                if audio_bytes:
                    # Drop oldest if full
                    if self._audio_queue.full():
                        try:
                            self._audio_queue.get_nowait()
                        except queue.Empty:
                            pass
                    self._audio_queue.put_nowait(audio_bytes)
            except Exception as e:
                logger.warning(f"[TTS] Server-side synthesis failed, falling back to browser: {e}")
                # Fallback: text is already in state, browser can pick it up

        # Local playback on server speakers (hardware mode)
        if use_local and self._tts:
            self._tts.speak(text)

        # Browser mode: text + seq already set above — client reads from WebSocket state

    def get_audio_chunk(self) -> Optional[bytes]:
        """Non-blocking: get next synthesized audio chunk for /ws/audio."""
        try:
            return self._audio_queue.get_nowait()
        except queue.Empty:
            return None

    def get_annotated_frame(self) -> Optional[bytes]:
        """Get the latest JPEG-encoded annotated frame."""
        with self._frame_lock:
            return self._latest_frame

    # ------------------------------------------------------------------
    # Browser camera support
    # ------------------------------------------------------------------

    def push_browser_frame(self, jpeg_bytes: bytes):
        """Push a JPEG frame received from the browser's WebSocket.

        Called by server.py /ws/camera endpoint. Drops old frames to
        avoid building up a backlog.
        """
        # Drop stale frame if queue is full (maxsize=2)
        try:
            self._browser_frame_queue.put_nowait(jpeg_bytes)
        except queue.Full:
            try:
                self._browser_frame_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._browser_frame_queue.put_nowait(jpeg_bytes)
            except queue.Full:
                pass

    def _browser_frame_source(self):
        """Generator that yields numpy frames decoded from browser JPEG bytes.

        Acts as a drop-in replacement for Camera.stream() when
        camera.mode is 'browser'.

        Also drains the query queue and answers queries via text-only
        LLM when no camera frames are available (fallback path).
        """
        import numpy as np
        no_frame_seconds = 0
        warned = False
        while self._running:
            try:
                jpeg_bytes = self._browser_frame_queue.get(timeout=0.5)
                no_frame_seconds = 0
                warned = False
                # Decode JPEG → numpy BGR frame
                arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is not None:
                    yield frame
                else:
                    logger.warning("[BrowserCam] Failed to decode JPEG frame")
            except queue.Empty:
                no_frame_seconds += 0.5
                if not warned and no_frame_seconds >= 3:
                    logger.warning(
                        "[BrowserCam] No frames received for 3s. "
                        "Ensure the browser has camera permission (requires HTTPS or localhost)."
                    )
                    warned = True

                # ── Fallback: answer pending queries without camera ──
                self._drain_queries_without_camera()
                continue

    def _drain_queries_without_camera(self):
        """Answer any pending user queries using text-only LLM (no camera frame).

        Called when browser camera frames are not arriving.  Provides a
        degraded but functional response path so queries don't hang forever.
        """
        try:
            query = self._query_queue.get_nowait()
        except queue.Empty:
            return

        logger.info(f"[Fallback] Answering query without camera frame: {query}")
        self._current_query = query
        self._pipeline_state["stt"]["active"] = True
        # Note: user message already added to dialogue_history by submit_query()

        try:
            self._pipeline_state["llm"]["active"] = True
            self._pipeline_state["llm"]["is_processing"] = True

            answer = self._fusion.handle_user_query(query)
            if not answer:
                answer = (
                    "I can't see right now — no camera feed is available. "
                    "Please grant camera permission in your browser, or check that "
                    "you're accessing the page over HTTPS / localhost."
                )

            self._current_response = answer
            with self._history_lock:
                self._dialogue_history.append({
                    "role": "ai",
                    "text": answer,
                    "timestamp": time.time(),
                })
            logger.info(f"[Fallback] LLM response: {answer[:120]}")
        except Exception as e:
            logger.error(f"[Fallback] LLM failed: {e}")
            fallback_msg = (
                "Camera feed not available. Please allow camera access in your browser "
                "(requires HTTPS or localhost)."
            )
            self._current_response = fallback_msg
            with self._history_lock:
                self._dialogue_history.append({
                    "role": "ai",
                    "text": fallback_msg,
                    "timestamp": time.time(),
                })
        finally:
            self._current_query = None
            self._pipeline_state["stt"]["active"] = False
            self._pipeline_state["llm"]["is_processing"] = False

    # ------------------------------------------------------------------
    # Main processing loop
    # ------------------------------------------------------------------

    def _main_loop(self, generation: int):
        """Background thread running the pipeline."""
        logger.info("[SystemManager] Main loop started")
        self._pipeline_state["camera"]["active"] = True

        # Select frame source based on camera mode
        if self._camera_mode == "browser":
            frame_source = self._browser_frame_source()
            logger.info("[SystemManager] Using browser camera frame source")
        else:
            frame_source = self._camera.stream()
            logger.info("[SystemManager] Using local camera frame source")

        try:
            for frame in frame_source:
                if not self._running or generation != self._run_generation:
                    break

                current_time = time.time()

                # --- YOLO Detection ---
                self._pipeline_state["yolo"]["active"] = True
                yolo_start = time.time()
                detections = self._detector.detect(frame)
                yolo_ms = (time.time() - yolo_start) * 1000
                self._pipeline_state["yolo"]["last_latency_ms"] = round(yolo_ms, 1)
                self._pipeline_state["yolo"]["detections_count"] = len(detections)
                self._detections = detections

                # Keep clean frame for VLM
                clean_frame = frame.copy()

                # Draw detections on display frame
                frame = self._draw_detections(frame, detections)

                # --- Safety Layer ---
                safety_result = self._safety.evaluate(detections)
                if safety_result:
                    alert_type, message = safety_result
                    self._pipeline_state["safety"]["active"] = True
                    self._pipeline_state["safety"]["last_alert"] = message
                    self._fusion.handle_safety_alert(message, alert_type)
                    self._latest_description = f"ALERT: {message}"
                else:
                    self._pipeline_state["safety"]["active"] = False
                    self._pipeline_state["safety"]["last_alert"] = None

                # --- Spatial Tracking ---
                self._fusion.update_spatial_context(detections, current_time, frame.shape[1])
                self._spatial_summary = self._fusion.get_spatial_summary()

                # --- Check for pending user queries ---
                try:
                    query = self._query_queue.get_nowait()
                    self._current_query = query
                    self._pipeline_state["stt"]["active"] = True

                    # Per architecture: just set pending_query on FusionEngine
                    # LLM only runs AFTER VLM provides scene description
                    self._fusion.set_pending_query(query)
                    logger.info(f"[Pipeline] Query pending for VLM grounding: {query}")

                    self._pipeline_state["stt"]["active"] = False
                except queue.Empty:
                    pass

                # --- Harvest LLM results from VLM-grounded queries (non-blocking) ---
                llm_result = self._llm_worker.get_result() if self._llm_worker else None
                if llm_result:
                    result_type, answer, llm_ms = llm_result
                    self._pipeline_state["llm"]["last_latency_ms"] = round(llm_ms, 1)
                    self._pipeline_state["llm"]["is_processing"] = False

                    if answer:
                        self._current_response = answer
                        with self._history_lock:
                            self._dialogue_history.append({
                                "role": "ai",
                                "text": answer,
                                "timestamp": time.time()
                            })
                        self._pipeline_state["tts"]["active"] = True
                        self._pipeline_state["tts"]["is_speaking"] = True
                        # Emit to remote clients
                        self.emit_tts(answer, priority="response")

                    self._current_query = None

                # --- VLM Processing ---
                is_critical = safety_result and safety_result[0] == "CRITICAL_ALERT"
                if not is_critical:
                    # Harvest VLM results
                    result = self._qwen_worker.get_result() if self._qwen_worker else None
                    if result:
                        new_desc, duration = result
                        self._pipeline_state["vlm"]["is_processing"] = False
                        self._pipeline_state["vlm"]["last_latency_ms"] = round(duration * 1000, 1)
                        self._latest_description = new_desc
                        logger.info(f"[Pipeline] VLM description ({duration:.1f}s): {new_desc[:100]}")

                        if self._current_query:
                            # Submit VLM-grounded LLM query (non-blocking)
                            if self._llm_worker and self._llm_worker.process_vlm_query(new_desc):
                                self._pipeline_state["llm"]["active"] = True
                                self._pipeline_state["llm"]["is_processing"] = True
                        else:
                            self._fusion.handle_scene_description(new_desc)

                    # Trigger VLM
                    has_query = self._current_query is not None
                    time_to_sample = self._sampler.should_sample()
                    should_run = False

                    if has_query:
                        should_run = True
                    elif time_to_sample:
                        # Run VLM on sampled frames — scene change is optional
                        # (first frame always sampled via FrameSampler)
                        if self._scene_detector.has_changed(clean_frame):
                            should_run = True
                        else:
                            logger.debug("[VLM] Sampled frame skipped (scene unchanged)")

                    if should_run:
                        context_str = ", ".join([d["label"] for d in detections])
                        if has_query:
                            context_str += f". USER QUESTION: {self._current_query}"

                        if self._qwen_worker and self._qwen_worker.process(clean_frame, context_str):
                            self._pipeline_state["vlm"]["active"] = True
                            self._pipeline_state["vlm"]["is_processing"] = True

                # --- Encode frame for MJPEG ---
                _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                with self._frame_lock:
                    self._latest_frame = jpeg.tobytes()

                # Throttle to ~30 FPS max
                time.sleep(0.001)

        except Exception as e:
            logger.error(f"[SystemManager] Main loop error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._running = False
            if generation == self._run_generation:
                self._system_status = "IDLE"
            self._pipeline_state["camera"]["active"] = False
            if self._camera:
                self._camera.release()
                self._camera = None  # Allow re-init on next start
            logger.info("[SystemManager] Main loop ended")

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _draw_detections(frame, detections: list) -> Any:
        """Draw YOLO bounding boxes on the frame."""
        for d in detections:
            x1, y1, x2, y2 = map(int, d["bbox"][0])
            label = d["label"]
            conf = d["confidence"]

            # Color by danger level
            lo = label.lower()
            if lo in {"knife", "gun", "fire", "stairs", "car", "bus", "truck", "bike"}:
                color = (0, 0, 255)
            elif lo in {"person", "dog", "animal", "bicycle", "wall", "glass"}:
                color = (0, 255, 255)
            elif lo in {"chair", "table", "bag"}:
                color = (255, 0, 0)
            else:
                color = (0, 255, 0)

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            text = f"{label} {conf:.2f}"
            cv2.rectangle(frame, (x1, y1 - 22), (x1 + len(text) * 9, y1), color, -1)
            cv2.putText(frame, text, (x1 + 2, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        return frame


class _QwenWorker:
    """Async VLM worker — runs VLM inference in a background thread."""

    def __init__(self, qwen_instance):
        self.qwen = qwen_instance
        self.input_queue = queue.Queue(maxsize=1)
        self.output_queue = queue.Queue(maxsize=4)
        self.running = True
        self.is_busy = False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _enqueue_result(self, result):
        try:
            self.output_queue.put_nowait(result)
        except queue.Full:
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                pass
            self.output_queue.put_nowait(result)

    def _run(self):
        while self.running:
            try:
                item = self.input_queue.get(timeout=0.1)
                frame, context_str = item
                self.is_busy = True
                try:
                    start = time.time()
                    logger.debug(f"[VLM] Processing frame ({frame.shape[1]}x{frame.shape[0]}) context='{context_str[:80]}...'")
                    desc = self.qwen.describe_scene(frame, context=context_str)
                    duration = time.time() - start
                    logger.info(f"[VLM] Result ({duration:.1f}s): {desc[:120]}")
                    self._enqueue_result((desc, duration))
                except Exception as e:
                    logger.error(f"[QwenWorker] VLM inference failed: {e}")
                    import traceback
                    traceback.print_exc()
                    # Put error result so main loop knows VLM finished
                    self._enqueue_result((f"VLM Error: {e}", 0.0))
                finally:
                    self.is_busy = False
                    self.input_queue.task_done()
            except queue.Empty:
                continue

    def process(self, frame, context_str: str) -> bool:
        if not self.is_busy and self.input_queue.empty():
            self.input_queue.put((frame.copy(), context_str))
            logger.debug(f"[VLM] Frame submitted to worker queue")
            return True
        return False

    def get_result(self):
        try:
            return self.output_queue.get_nowait()
        except queue.Empty:
            return None

    def stop(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=1)


class _LLMWorker:
    """Async LLM worker — runs LLM queries in a background thread.

    Accepts two types of requests:
    - 'query': Immediate LLM response to user query (handle_user_query)
    - 'vlm_query': VLM-grounded LLM response (handle_vlm_description)

    Results are tuples of (result_type, answer_text, latency_ms).
    """

    def __init__(self, fusion_engine):
        self.fusion = fusion_engine
        self.input_queue = queue.Queue(maxsize=1)
        self.output_queue = queue.Queue(maxsize=4)
        self.running = True
        self.is_busy = False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _enqueue_result(self, result):
        try:
            self.output_queue.put_nowait(result)
        except queue.Full:
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                pass
            self.output_queue.put_nowait(result)

    def _run(self):
        while self.running:
            try:
                item = self.input_queue.get(timeout=0.1)
                request_type, payload = item
                self.is_busy = True
                try:
                    start = time.time()
                    if request_type == "query":
                        answer = self.fusion.handle_user_query(payload)
                        result_type = "immediate"
                    elif request_type == "vlm_query":
                        answer = self.fusion.handle_vlm_description(payload)
                        result_type = "vlm_grounded"
                    else:
                        answer = None
                        result_type = "unknown"

                    latency_ms = (time.time() - start) * 1000
                    self._enqueue_result((result_type, answer, latency_ms))
                except Exception as e:
                    logger.error(f"[LLMWorker] {e}")
                    import traceback
                    traceback.print_exc()
                finally:
                    self.is_busy = False
                    self.input_queue.task_done()
            except queue.Empty:
                continue

    def process_query(self, query: str) -> bool:
        """Submit a user query for immediate LLM response."""
        if not self.is_busy and self.input_queue.empty():
            self.input_queue.put(("query", query))
            return True
        return False

    def process_vlm_query(self, vlm_description: str) -> bool:
        """Submit a VLM-grounded query for LLM reasoning."""
        if not self.is_busy and self.input_queue.empty():
            self.input_queue.put(("vlm_query", vlm_description))
            return True
        return False

    def get_result(self):
        """Non-blocking: get completed LLM result, or None."""
        try:
            return self.output_queue.get_nowait()
        except queue.Empty:
            return None

    def stop(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=1)
