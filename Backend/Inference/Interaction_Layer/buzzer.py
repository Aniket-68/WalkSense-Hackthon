from loguru import logger

class Buzzer:
    def beep(self, pattern):
        logger.debug(f"[BUZZER] pattern={pattern}")
