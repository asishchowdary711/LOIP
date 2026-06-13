class GraphSAGEWrapper:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode

    def predict_fraud(self, node_features: dict, graph_context: dict) -> float:
        if self.mock_mode:
            # Mock fraud probability (0.0 = clean, 1.0 = fraud)
            return 0.05
        return 0.0
