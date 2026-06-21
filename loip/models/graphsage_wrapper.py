from pathlib import Path

CHECKPOINT_DIR = Path(__file__).resolve().parent / "checkpoints"
CHECKPOINT_PATH = CHECKPOINT_DIR / "graphsage_fraud.joblib"

# Fixed feature order — must match scripts/training/train_fraud_graphsage.py
# and scripts/training/generate_synthetic_dataset.py.
FEATURE_ORDER = ["pan_match_count", "aadhaar_match_count", "total_degree"]

MOCK_PREDICTION = 0.05

# Identifier fields used to link applications into a shared-identifier graph.
IDENTIFIER_FIELDS = ["pan", "aadhaar"]


class GraphSAGEWrapper:
    """Simplified message-passing approximation: maintains an in-memory graph
    of applications seen so far (no Neo4j dependency). Edges connect
    applications that share a non-empty pan or aadhaar value — a signal for
    synthetic-identity/collusion rings.
    """

    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self._model = None

        # node_id -> {"pan": str, "aadhaar": str}
        self._nodes: dict[str, dict] = {}

        if not self.mock_mode:
            try:
                import sklearn  # noqa: F401
            except ImportError:
                self.mock_mode = True

    def _load_model(self):
        if self._model is not None:
            return self._model

        if not CHECKPOINT_PATH.exists():
            return None

        import joblib

        self._model = joblib.load(CHECKPOINT_PATH)
        return self._model

    def _graph_features(self, application_id: str, node_features: dict) -> dict[str, int]:
        new_pan = node_features.get("pan", "")
        new_aadhaar = node_features.get("aadhaar", "")

        # Deduplicate by (pan, aadhaar): if the same identity already exists
        # under a different application_id, treat this submission as the same
        # applicant — drop the older node so the same person re-submitting
        # their own docs doesn't look like a synthetic-identity ring.
        if new_pan and new_aadhaar:
            for dup_id in [
                other_id for other_id, other in self._nodes.items()
                if other_id != application_id
                and other.get("pan") == new_pan
                and other.get("aadhaar") == new_aadhaar
            ]:
                self._nodes.pop(dup_id, None)

        self._nodes[application_id] = {
            field: node_features.get(field, "") for field in IDENTIFIER_FIELDS
        }

        pan_match_count = 0
        aadhaar_match_count = 0
        neighbors: set[str] = set()

        pan = self._nodes[application_id]["pan"]
        aadhaar = self._nodes[application_id]["aadhaar"]

        for other_id, other in self._nodes.items():
            if other_id == application_id:
                continue
            matched = False
            if pan and other["pan"] == pan:
                pan_match_count += 1
                matched = True
            if aadhaar and other["aadhaar"] == aadhaar:
                aadhaar_match_count += 1
                matched = True
            if matched:
                neighbors.add(other_id)

        return {
            "pan_match_count": pan_match_count,
            "aadhaar_match_count": aadhaar_match_count,
            "total_degree": len(neighbors),
        }

    def reset_graph(self) -> int:
        """Clear the in-memory application graph. Returns the prior node count.
        Useful between demo runs when the same applicant submits repeatedly —
        each retest would otherwise look like a fraud-ring match against the
        previous attempt."""
        n = len(self._nodes)
        self._nodes.clear()
        return n

    def predict_fraud(self, node_features: dict, graph_context: dict) -> float:
        application_id = graph_context.get("application_id")
        if not application_id:
            return MOCK_PREDICTION

        features = self._graph_features(application_id, node_features)

        if self.mock_mode:
            return MOCK_PREDICTION

        model = self._load_model()
        if model is None:
            return MOCK_PREDICTION

        import numpy as np

        ordered = np.array([[float(features[name]) for name in FEATURE_ORDER]])
        prediction = model.predict_proba(ordered)
        return float(prediction[0][1])
