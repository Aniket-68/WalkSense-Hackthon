from loguru import logger

class LED:
    def on(self, color):
        logger.debug(f"[LED] color={color}")
