from difflib import SequenceMatcher
import time

class ContextManager:
    def __init__(self):
        self.last_description = ""
        self.last_description_time = 0
        self.history = []
        self.max_history = 5
        self.silence_until = 0

    def set_silence_window(self, duration=5):
        """Block low-priority messages for 'duration' seconds"""
        self.silence_until = time.time() + duration

    def is_silenced(self):
        return time.time() < self.silence_until

    def _normalize(self, text):
        import re
        # Remove punctuation and lowercase
        return re.sub(r'[^\w\s]', '', text.lower())

    def is_redundant(self, text, threshold=0.6, timeout=10):
        """
        Check if the text is redundant OR if we are in a silence window.
        """
        if self.is_silenced():
            return True # Treat as redundant to suppress it
            
        if not text:
            return True

        current_time = time.time()
        
        # If it's been a long time, nothing is redundant
        if current_time - self.last_description_time > timeout:
            return False

        # Compare normalized versions
        norm_text = self._normalize(text)
        norm_last = self._normalize(self.last_description)
        
        similarity = SequenceMatcher(None, norm_last, norm_text).ratio()
        
        if similarity > threshold:
            from loguru import logger
            logger.debug(f"Context: Redundant ({int(similarity*100)}%): '{text[:30]}...'")
            return True
            
        return False

    def update_context(self, text):
        """Update the context with the spoken text"""
        self.last_description = text
        self.last_description_time = time.time()
        self.history.append(text)
        if len(self.history) > self.max_history:
            self.history.pop(0)
