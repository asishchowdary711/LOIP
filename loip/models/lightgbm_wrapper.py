class LightGBMWrapper:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        
    def predict(self, features: dict) -> float:
        if self.mock_mode:
            return 0.85
        return 0.0
