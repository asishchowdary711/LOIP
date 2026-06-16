import numpy as np


class ArcFaceWrapper:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self._app = None

    def _get_app(self):
        if self._app is None:
            try:
                from insightface.app import FaceAnalysis
                self._app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
                self._app.prepare(ctx_id=-1, det_size=(320, 320))
            except Exception:
                pass
        return self._app

    def _get_embedding(self, img: np.ndarray):
        app = self._get_app()
        if app is None:
            return None
        faces = app.get(img)
        if not faces:
            return None
        emb = faces[0].embedding
        norm = np.linalg.norm(emb)
        return emb / norm if norm > 0 else emb

    def verify_face(self, img1: np.ndarray, img2: np.ndarray) -> float:
        if self.mock_mode:
            return 0.95
        emb1 = self._get_embedding(img1)
        emb2 = self._get_embedding(img2)
        if emb1 is None or emb2 is None:
            return 0.0
        # Cosine similarity, clamped to [0, 1]
        return float(np.clip(np.dot(emb1, emb2), 0.0, 1.0))
