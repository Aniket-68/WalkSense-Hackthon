from loguru import logger

class Haptics:
    def vibrate(self, intensity):
        logger.debug(f"[HAPTIC] intensity={intensity}")
