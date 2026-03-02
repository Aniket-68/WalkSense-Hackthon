# interaction/listening_layer.py

import speech_recognition as sr
import os
from Perception_Layer.alerts import AlertEvent
from loguru import logger

class STTListener:
    """
    Converts user voice into text (on-demand)
    """

    def __init__(self):
        from Infrastructure.config import Config
        self.recognizer = sr.Recognizer()
        
        # New Top-Level Microphone Config:
        self.device_index = Config.get("microphone.hardware.id") if Config.get("microphone.mode") == "hardware" else None
        self.cal_duration = Config.get("microphone.hardware.calibration_duration", 2.0)
        self.energy_thresh = Config.get("microphone.hardware.energy_threshold", 50)
        self.pause_thresh = Config.get("microphone.hardware.pause_threshold", 1.0)
        self.dynamic_energy = Config.get("microphone.hardware.dynamic_energy", True)
        
        try:
            self.mic = sr.Microphone(device_index=self.device_index)
            # Log the device name for confirmation
            mics = sr.Microphone.list_microphone_names()
            dev_name = mics[self.device_index] if (self.device_index is not None and self.device_index < len(mics)) else "System Default"
            logger.info(f"Initialized Microphone ID: {self.device_index} ({dev_name})")
        except Exception as e:
            logger.error(f"Failed to init mic {self.device_index}: {e}")
            self.mic = sr.Microphone() # Fallback

        from Infrastructure.config import Config
        self.config = Config

        # Pre-load model to prevent lag on first query
        self._preload_model()
        
    def listen_once(self, timeout=None):
        from Infrastructure.config import Config
        provider = Config.get("stt.active_provider", "local")
        config_path = f"stt.providers.{provider}"
        
        if timeout is None:
            timeout = Config.get(f"{config_path}.timeout", 10)
        
        limit = Config.get(f"{config_path}.phrase_time_limit", 15)

        try:
            with self.mic as source:
                # Reduce calibration to 0.5s for faster response
                logger.debug(f"Calibrating for environment noise (0.5s)...")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                
                # Apply config settings
                self.recognizer.energy_threshold = self.energy_thresh
                self.recognizer.dynamic_energy_threshold = self.dynamic_energy
                self.recognizer.pause_threshold = self.pause_thresh
                self.recognizer.non_speaking_duration = 0.5
                
                logger.info(f"LISTENING NOW ({provider}). SPEAK...")
                # Reduce timeout to fail fast if silence. Increase phrase_time_limit for long queries.
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                logger.info("Recording finished. Transcribing...")
            
            # Route to appropriate recognition method
            detailed_info = ""
            if provider == "google":
                text = self.recognizer.recognize_google(audio)
                detailed_info = "Language: en-US (Google Default)"
            
            elif provider == "whisper_api":
                # ... (rest of whisper_api logic)
                api_key = os.getenv(Config.get(f"{config_path}.api_key_env", "OPENAI_API_KEY"))
                if not api_key:
                    print("[STT ERROR] OPENAI_API_KEY not set in environment")
                    return None
                
                text = self.recognizer.recognize_whisper_api(
                    audio,
                    api_key=api_key,
                    model=Config.get(f"{config_path}.model", "whisper-1"),
                    language=Config.get(f"{config_path}.language", "en")
                )
                detailed_info = f"Provider: Whisper API"
            
            elif provider == "local":
                # Local Whisper (faster-whisper or OpenAI whisper)
                # Resolve model_size from nested active_model -> models dict
                _active = Config.get(f"{config_path}.active_model")
                _model_size = Config.get(f"{config_path}.models.{_active}.model_size", "small") if _active else Config.get(f"{config_path}.model_size", "small")
                _device = Config.get(f"{config_path}.device", "cuda")
                _compute = Config.get(f"{config_path}.compute_type", "int8")
                _lang = Config.get(f"{config_path}.language", "en")
                try:
                    # Try faster-whisper first (much faster)
                    text, lang_info = self._recognize_faster_whisper(
                        audio,
                        model_size=_model_size,
                        device=_device,
                        compute_type=_compute,
                        language=_lang
                    )
                    detailed_info = lang_info
                except Exception as e:
                    # Fallback to OpenAI's whisper
                    logger.warning(f"[STT] Faster-Whisper failed ({e}). Falling back to OpenAI Whisper.")
                    try:
                        text, lang_info = self._recognize_openai_whisper(
                            audio,
                            model_size=_model_size,
                            language=_lang
                        )
                        detailed_info = lang_info
                    except Exception as e_openai:
                        logger.error(f"[STT] OpenAI Whisper failed ({e_openai}). Fallback to Google.")
                        # Ultimate Fallback: Google
                        text = self.recognizer.recognize_google(audio)
                        detailed_info = "Google (Fallback)"
            
            else:
                print(f"[STT ERROR] Unknown provider: {provider}")
                return None
            
            if text:
                logger.info(f"STT | {detailed_info} | USER SAID: {text}")
            else:
                logger.info("No text transcribed.")
                
            return text
            
        except sr.WaitTimeoutError:
            print("[STT] Timeout: No speech detected")
            return None
        except Exception as e:
            print(f"[STT ERROR] {e}")
            return None
    
    def _preload_model(self):
        """Pre-load and cache the model during initialization"""
        try:
            provider = self.config.get("stt.active_provider", "local")
            if provider == "local":
                path = "stt.providers.local"
                # Resolve model_size from nested active_model -> models dict
                _active = self.config.get(f"{path}.active_model")
                size = self.config.get(f"{path}.models.{_active}.model_size", "small") if _active else self.config.get(f"{path}.model_size", "small")
                dev = self.config.get(f"{path}.device", "cuda")
                ctype = self.config.get(f"{path}.compute_type", "int8")
                
                logger.info(f"[STT] Pre-loading model '{size}' on {dev}...")
                
                # Check priority: Faster-Whisper -> OpenAI Whisper
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                model_dir = os.path.join(project_root, "Models", "stt")
                
                try:
                    from faster_whisper import WhisperModel
                    self._whisper_model = WhisperModel(size, device=dev, compute_type=ctype, download_root=model_dir)
                    self._whisper_model_size = size
                    self._backend = "faster_whisper"
                    logger.info(f"[STT] Faster-Whisper Loaded Successfully ({size})")
                except Exception as e:
                    logger.warning(f"[STT] Faster-Whisper failed ({e}). Falling back to OpenAI Whisper.")
                    import whisper
                    
                    # Ensure we use the local file if it exists
                    # OpenAI Whisper expects download_root to contain the .pt file
                    self._whisper_model = whisper.load_model(size, download_root=model_dir)
                    self._whisper_model_size = size
                    self._backend = "openai_whisper"
                    logger.info(f"[STT] OpenAI Whisper Loaded Successfully ({size})")
                    
        except Exception as e:
            logger.error(f"[STT] Pre-loading failed: {e}")

    def _recognize_faster_whisper(self, audio, model_size="small", device="cuda", compute_type="int8", language="en"):
        """Use faster-whisper for local transcription (recommended)"""
        from faster_whisper import WhisperModel
        import io
        import wave
        
        # Convert AudioData to WAV bytes
        wav_data = io.BytesIO(audio.get_wav_data())
        
        # Load model (cached after first use)
        
        # Load model (if not pre-loaded or size changed)
        if not hasattr(self, '_whisper_model') or self._whisper_model_size != model_size:
            # Re-load using helper logic (simplified here for brevity, usually calls _preload)
            self._whisper_model_size = model_size
             # Use the local models directory
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            model_dir = os.path.join(project_root, "Models", "stt")
            # Use provided compute_type or default logic
            try:
                self._whisper_model = WhisperModel(model_size, device=device, compute_type=compute_type, download_root=model_dir)
                logger.info(f"[STT] Loaded Faster-Whisper model '{model_size}' on {device}")
            except Exception:
                # If int8/cuda fails, fallback to cpu/int8 or float32
                logger.warning("STT: GPU/Int8 failed, falling back to CPU")
                self._whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8", download_root=model_dir)
        
        # Transcribe
        segments, info = self._whisper_model.transcribe(wav_data, language=language)
        text = " ".join([segment.text for segment in segments])
        
        lang_info = f"Detected: {info.language} ({int(info.language_probability*100)}% prob)"
        return text.strip(), lang_info
    
    def _recognize_openai_whisper(self, audio, model_size="small", language="en"):
        """Fallback: Use OpenAI's whisper for local transcription"""
        import whisper
        import io
        import tempfile
        
        # Load model (cached)
        if (not hasattr(self, '_whisper_model') or 
            self._whisper_model_size != model_size or 
            getattr(self, '_backend', '') != "openai_whisper"):
            
            logger.info(f"[STT] Loading OpenAI Whisper model: {model_size} from Models/stt")
            # Use the local models directory
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            model_dir = os.path.join(project_root, "Models", "stt")
            
            import whisper
            self._whisper_model = whisper.load_model(model_size, download_root=model_dir)
            self._whisper_model_size = model_size
            self._backend = "openai_whisper"
        
        # Save audio to temp file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio.get_wav_data())
            temp_path = f.name
        
        try:
            # Explicitly cast to FP32 if needed to avoid FP16 warnings on CPU
            result = self._whisper_model.transcribe(temp_path, language=language, fp16=False)
            
            logger.info(f"[STT DEBUG] Whisper Result Type: {type(result)}")
            if hasattr(result, "keys"):
                logger.info(f"[STT DEBUG] Keys: {result.keys()}")
            else:
                logger.info(f"[STT DEBUG] Result: {result}")

            # Handel Dict vs Object vs Tuple
            if isinstance(result, dict):
                text = result["text"].strip()
                lang_info = f"Detected: {result.get('language', 'unknown')}"
            else:
                # If it returns a tuple (unlikely for openai-whisper but possible if version mixup)
                logger.warning(f"[STT] Unexpected result type: {type(result)}")
                text = str(result)
                lang_info = "Unknown"

            return text, lang_info
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class ListeningLayer:
    """
    Orchestrates STT input and TTS output
    Handles events from FusionEngine
    """

    def __init__(self, tts_engine, fusion_engine):
        self.tts = tts_engine
        self.fusion = fusion_engine
        self.stt = STTListener()

    def listen_for_query(self):
        """Listen for user voice query and process it"""
        query = self.stt.listen_once()
        if query:
            print(f"[ListeningLayer] Processing query: {query}")
            self.fusion.handle_user_query(query)

    def handle_event(self, event: AlertEvent):
        """Handle events from FusionEngine and speak them out"""
        logger.info(f"Interaction Event: {event.message}")
        self.tts.speak(event.message)
