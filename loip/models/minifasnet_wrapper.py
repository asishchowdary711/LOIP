import numpy as np

class MiniFASNetWrapper:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode

    def detect_liveness(self, img: np.ndarray) -> float:
        if self.mock_mode:
            # Mock liveness score (1.0 = live, 0.0 = spoof)
            return 0.98
        return 0.0
