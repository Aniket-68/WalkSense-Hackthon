# interaction/aux_controller.py

from Interaction_Layer.haptics import Haptics
from Interaction_Layer.buzzer import Buzzer
from Interaction_Layer.led import LED

class AuxController:
    def __init__(self):
        self.haptics = Haptics()
        self.buzzer = Buzzer()
        self.led = LED()

    def trigger_haptic(self, intensity):
        self.haptics.vibrate(intensity)

    def trigger_buzzer(self, pattern):
        self.buzzer.beep(pattern)

    def trigger_led(self, color):
        self.led.on(color)
