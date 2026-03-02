# inference/runtime_state.py

import time
from collections import defaultdict

class RuntimeState:
    """
    Manages runtime state to prevent alert spam.
    Throttles repeated alerts of the same type.
    """

    def __init__(self, cooldown_seconds=None):
        """
        Args:
            cooldown_seconds: Minimum time between identical alerts
        """
        from Infrastructure.config import Config
        self.cooldown_seconds = cooldown_seconds or Config.get("safety.alert_cooldown", 10.0)
        self.last_alert_time = defaultdict(float)

    def should_emit(self, alert_type, message=None):
        """
        Check if enough time has passed since last alert of this type/content.
        """
        current_time = time.time()
        
        # Create a unique key for this specific alert
        # If message is provided, throttle based on content.
        # Otherwise fall back to throttline by type.
        key = f"{alert_type}:{message}" if message else alert_type
        
        last_time = self.last_alert_time[key]
        
        # Check if cooldown period has passed
        if current_time - last_time >= self.cooldown_seconds:
            self.last_alert_time[key] = current_time
            return True
        
        return False

    def reset(self):
        """Reset all alert timers"""
        self.last_alert_time.clear()

    def set_cooldown(self, alert_type, cooldown_seconds):
        """
        Set custom cooldown for specific alert type.
        
        Args:
            alert_type: Type of alert
            cooldown_seconds: Cooldown duration in seconds
        """
        # This would require a more complex implementation
        # For now, we use a global cooldown
        pass
