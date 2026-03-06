"""Fusion Layer: Central orchestration for WalkSense AI system."""

from typing import Optional, List, Dict, Any
import threading
from Perception_Layer.alerts import AlertEvent
from Fusion_Layer.state import RuntimeState
from Fusion_Layer.router import DecisionRouter
from Reasoning_Layer.llm import LLMReasoner
from Fusion_Layer.context import SpatialContextManager


class FusionEngine:
    """Central coordinator for perception, reasoning, and interaction subsystems.
    
    The FusionEngine orchestrates the flow of information between:
    - Perception Layer (object detection, safety alerts)
    - Reasoning Layer (VLM scene description, LLM query answering)
    - Interaction Layer (TTS, haptics)
    
    Attributes:
        router: DecisionRouter for alert prioritization and routing
        runtime: RuntimeState for managing alert cooldowns
        llm: LLMReasoner for contextual query answering
        spatial: SpatialContextManager for object tracking
        pending_query: Current user query awaiting VLM response
    """
    
    def __init__(self, 
                 tts_engine: Any,
                 llm_backend: str = "lm_studio",
                 llm_url: str = "http://localhost:1234/v1",
                 llm_model: str = "qwen/qwen3-vl-4b",
                 llm_api_key: Optional[str] = None,
                 depth_estimator: Any = None) -> None:
        """Initialize fusion engine with TTS and LLM configuration.
        
        Args:
            tts_engine: TTSEngine instance for audio output
            llm_backend: LLM provider ('lm_studio', 'ollama', 'gemini', 'openai')
            llm_url: API endpoint URL for LLM backend
            llm_model: Model identifier for LLM
            llm_api_key: API key for Gemini or OpenAI (optional, can use env var)
            depth_estimator: Optional DepthEstimator instance for metric depth
        """
        self.router = DecisionRouter(tts_engine)
        self.runtime = RuntimeState()
        
        # Enhanced Reasoning Modules
        self.llm = LLMReasoner(backend=llm_backend, api_url=llm_url, model_name=llm_model, api_key=llm_api_key)
        self.spatial = SpatialContextManager(depth_estimator=depth_estimator)
        self.depth_estimator = depth_estimator
        
        # State for query handling
        self.pending_query = None
        self._pending_query_lock = threading.Lock()

    def set_pending_query(self, query: Optional[str]) -> None:
        with self._pending_query_lock:
            self.pending_query = query

    def get_pending_query(self) -> Optional[str]:
        with self._pending_query_lock:
            return self.pending_query

    def consume_pending_query(self) -> Optional[str]:
        with self._pending_query_lock:
            query = self.pending_query
            self.pending_query = None
            return query

    def handle_safety_alert(self, message: str, alert_type: str = "CRITICAL_ALERT") -> None:
        """Process and route immediate safety hazards.
        
        Args:
            message: Human-readable alert description
            alert_type: Severity level ('CRITICAL_ALERT', 'WARNING', 'INFO')
            
        Note:
            Alerts are subject to cooldown periods managed by RuntimeState
            to prevent spam. CRITICAL_ALERT typically overrides mute.
        """
        event = AlertEvent(alert_type, message)
        
        # Only emit if it passes the system-level cooldown (RuntimeState)
        if self.runtime.should_emit(event.type, message):
            self.router.route(event)

    def update_spatial_context(self, 
                                detections: List[Dict[str, Any]], 
                                timestamp: float, 
                                frame_width: int = 1280,
                                frame: Any = None) -> None:
        """Update object tracking and spatial-temporal awareness.
        
        Args:
            detections: List of detection dicts from YoloDetector
            timestamp: Current Unix timestamp
            frame_width: Frame width in pixels for direction calculation
            frame: Optional BGR frame for depth estimation
            
        Side Effects:
            - Runs depth estimation on the frame (if enabled)
            - Updates spatial context manager's object tracking
            - Generates proximity warnings for close objects
            - Routes warnings through DecisionRouter
        """
        # Run depth estimation if frame provided
        if frame is not None:
            self.spatial.update_depth_map(frame)

        events = self.spatial.update(detections, timestamp, frame_width)
        
        # If any new/moved objects are 'Close', tell the router
        for event in events:
            if event["distance"] in ["very close", "close"]:
                msg = f"{event['label']} {event['distance']} to your {event['direction']}"
                self.router.route(AlertEvent("WARNING", msg))

    def get_spatial_summary(self) -> str:
        """Get concise spatial state summary for UI display.
        
        Returns:
            Comma-separated string of tracked objects with directions
            (e.g., 'person left, chair center')
        """
        return self.spatial.get_summary()

    def handle_vlm_description(self, text: str) -> str:
        """Process VLM scene description and generate response.
        
        Decides whether to:
        - Answer pending user query (if exists)
        - Provide passive scene description (normal mode)
        
        Args:
            text: Scene description from Vision-Language Model
            
        Returns:
            LLM-generated answer (if query pending) or original description
            
        Side Effects:
            - Clears pending_query if answered
            - Updates spatial scene memory
            - Routes response through DecisionRouter
        """
        # Save to memory
        self.spatial.add_scene_description(text)
        
        pending_query = self.consume_pending_query()
        if pending_query:
            # We were waiting for a fresh description to answer a user query!
            ans = self._generate_llm_answer(pending_query, text)
            return ans
        else:
            # Regular passive description
            # event = AlertEvent("SCENE_DESC", text)
            # self.router.route(event) # DISABLED: User requested to avoid speaking VLM output (silent context update)
            return text

    def handle_scene_description(self, text: str) -> None:
        """Compatibility wrapper for handle_vlm_description.
        
        Args:
            text: Scene description text
        """
        self.handle_vlm_description(text)

    def handle_user_query(self, query: str) -> Optional[str]:
        """Process user voice query with immediate LLM response.
        
        Provides two-stage response:
        1. Immediate LLM answer based on current spatial context
        2. VLM-grounded refinement when next frame is processed
        
        Args:
            query: Transcribed user question from STT
            
        Side Effects:
            - Generates immediate LLM response
            - Sets self.pending_query for VLM-grounded follow-up
            - Routes responses through DecisionRouter
        """
        from loguru import logger
        
        # Get current spatial context
        spatial_ctx = self.spatial.get_context_for_llm()
        
        # Generate immediate LLM response using available context
        logger.info(f"[FUSION] Generating immediate LLM response for: {query}")
        try:
            immediate_answer = self.llm.answer_query(
                user_query=query,
                spatial_context=spatial_ctx,
                scene_description="Current spatial tracking data only. Visual confirmation pending."
            )
            
            # Send immediate response
            response_event = AlertEvent("RESPONSE", immediate_answer)
            # self.router.route(response_event) # DISABLED: User wants only VLM-grounded answer spoken
            logger.info(f"[FUSION] Immediate answer (Silent): {immediate_answer}")
            
        except Exception as e:
            logger.error(f"[FUSION] Failed to generate immediate answer: {e}")
            # Fallback acknowledgment
            ack_event = AlertEvent("RESPONSE", f"Checking on: {query}")
            # self.router.route(ack_event) # DISABLED
        
        # Keep query pending for VLM-grounded refinement
        self.set_pending_query(query)
        logger.info(f"[FUSION] Query pending for VLM refinement")
        
        return locals().get("immediate_answer", None)

    def _generate_llm_answer(self, query: str, vlm_desc: str) -> str:
        """Generate query response using LLM with visual and spatial grounding.
        
        Combines:
        - User query
        - VLM scene description 
        - Spatial context (object tracking, recent events)
        
        Includes factual grounding check to prevent hallucination.
        
        Args:
            query: User's question
            vlm_desc: Current VLM scene description
            
        Returns:
            Natural language answer grounded in visual evidence
            
        Note:
            If numeric mismatch detected between query and VLM,
            overrides LLM response with correction.
        """
        spatial_ctx = self.spatial.get_context_for_llm()
        
        # Use LLM to reason over everything
        answer = self.llm.answer_query(
            user_query=query,
            spatial_context=spatial_ctx,
            scene_description=vlm_desc
        )

        # FACTUAL GROUNDING CHECK (Anti-Hallucination)
        # If the LLM says "Yes" but VLM mentions a different number than the query, flag it.
        # Example: Query has "50", VLM has "100", LLM says "Yes".
        import re
        numbers_in_query = re.findall(r'\d+', query)
        if numbers_in_query:
            for num in numbers_in_query:
                # If query mentions a number not in VLM, but LLM is being positive...
                if num not in vlm_desc and ("yes" in answer.lower() or "confirm" in answer.lower()):
                    vlm_nums = re.findall(r'\d+', vlm_desc)
                    if vlm_nums:
                        correction = f"Wait, the camera actually sees {vlm_nums[0]}. Not {num}."
                        from loguru import logger
                        logger.warning(f"Grounding Alert: Hallucination detected for {num}. Overriding LLM.")
                        answer = correction
                        break
        
        # Send the final 'thought' to the router
        self.router.route(AlertEvent("RESPONSE", answer))
        return answer

    def handle_user_query_response(self, text: str) -> None:
        """Manually inject query response (override or fallback).
        
        Args:
            text: Response text to speak
        """
        event = AlertEvent("RESPONSE", text)
        self.router.route(event)
