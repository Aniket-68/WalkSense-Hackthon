from Interaction_Layer.tts import TTSEngine
from Fusion_Layer.redundancy import ContextManager
from Interaction_Layer.auxiliary import AuxController

class DecisionRouter:
    def __init__(self, tts_engine, remote_tts_callback=None):
        self.tts = tts_engine
        self._remote_tts = remote_tts_callback   # callable(text, priority)
        self.context_manager = ContextManager()
        self.aux = AuxController() # Initialize Auxiliary Controller
        self.muted = False

    def set_remote_tts(self, callback):
        """Set or update the remote TTS callback (manager.emit_tts)."""
        self._remote_tts = callback

    def _speak(self, text: str, priority: str = "response"):
        """Route speech to local TTS and/or remote callback."""
        if self._remote_tts:
            self._remote_tts(text, priority)
        else:
            # Fallback to local-only
            self.tts.speak(text)

    def toggle_mute(self):
        self.muted = not self.muted
        # Speak the status BEFORE the mute takes effect
        if self.muted:
            self._speak("Audio Muted", "info")
            # Give time for the message to be queued, then stop any other pending messages
        else:
            self._speak("Audio Active", "info")
        return self.muted
        
    def route(self, event):
        """
        Route an event to Interaction Layer (TTS + Aux) based on priority.
        """
        from Infrastructure.config import Config
        suppress = Config.get("safety.suppression.enabled", False)
        warn_thresh = Config.get("safety.suppression.redundancy_threshold", 0.8)
        warn_timeout = Config.get("safety.suppression.warning_timeout", 5.0)
        scene_timeout = Config.get("safety.suppression.scene_timeout", 20.0)

        severity = event.type
        message = event.message
        
        # 1. CRITICAL SAFETY: Strong Feedback (Overrides Mute)
        if severity == "CRITICAL_ALERT":
            self.aux.trigger_haptic("HIGH")
            self.aux.trigger_buzzer("ALARM")
            
            self._speak(f"Danger! {message}", "critical")
            self.context_manager.update_context(message)
            return

        # Check Mute for non-critical events
        if self.muted:
            return

        # 2. WARNINGS: Medium Feedback
        if severity == "WARNING":
            if not self.context_manager.is_redundant(message, threshold=warn_thresh, timeout=warn_timeout):
                self.aux.trigger_haptic("MEDIUM")
                self.aux.trigger_buzzer("WARNING")
                
                self._speak(f"Warning! {message}", "warning")
                self.context_manager.update_context(message)
            return

        # 3. RESPONSE (Generic): Confirmation Feedback from AI
        if severity == "RESPONSE":
             from loguru import logger
             logger.info(f"[ROUTER] Routing RESPONSE: {message}")
             self.aux.trigger_haptic("PULSE")
             self._speak(message, "response")
             self.context_manager.update_context(message)
             self.context_manager.set_silence_window(8)
             return

        # 4. INFO (Safety): Low Priority Object Detection
        if severity == "INFO":
             # Apply redundancy check to basic object detection alerts
             if not self.context_manager.is_redundant(message, threshold=warn_thresh, timeout=warn_timeout):
                 self.aux.trigger_haptic("PULSE")
                 self._speak(message, "info")
                 self.context_manager.update_context(message)
             return

        # 4. SCENE DESCRIPTION: No Physical Feedback (Passive)
        if severity == "SCENE_DESC":
            from loguru import logger
            # Strict Redundancy Check
            if not self.context_manager.is_redundant(message, threshold=warn_thresh - 0.1, timeout=scene_timeout):
                logger.info(f"[ROUTER] Routing SCENE_DESC: {message[:80]}...")
                self._speak(message, "scene")
                self.context_manager.update_context(message)
            else:
                logger.debug(f"[ROUTER] SCENE_DESC suppressed (redundant): {message[:50]}...")
            return
