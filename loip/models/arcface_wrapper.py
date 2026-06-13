import numpy as np

class ArcFaceWrapper:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode

    def verify_face(self, img1: np.ndarray, img2: np.ndarray) -> float:
        if self.mock_mode:
            # Mock similarity score
            return 0.95
        return 0.0
