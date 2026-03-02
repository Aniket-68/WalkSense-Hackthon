# utils/frame_sampler.py

class FrameSampler:
    """
    Controls how often expensive models (Qwen) are run
    """

    def __init__(self, every_n_frames=10):
        self.every_n_frames = every_n_frames
        self.counter = 0
        self._first_call = True

    def should_sample(self):
        # Always process the very first frame so VLM starts immediately
        if self._first_call:
            self._first_call = False
            return True
        self.counter += 1
        if self.counter >= self.every_n_frames:
            self.counter = 0
            return True
        return False
