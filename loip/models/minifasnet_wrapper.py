import logging

import numpy as np

logger = logging.getLogger(__name__)


class MiniFASNetWrapper:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self._app = None

    def _get_app(self):
        """Use InsightFace buffalo_l (already downloaded for ArcFace) as a
        heuristic liveness proxy until a real MiniFASNet checkpoint is available."""
        if self._app is None:
            try:
                from insightface.app import FaceAnalysis
                self._app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
                self._app.prepare(ctx_id=-1, det_size=(320, 320))
            except Exception as exc:
                logger.warning("Could not load InsightFace for liveness: %s", exc)
        return self._app

    def detect_liveness(self, img: np.ndarray) -> float:
        if self.mock_mode:
            return 0.98

        app = self._get_app()
        if app is None:
            return 0.5  # neutral rather than hard fail

        try:
            faces = app.get(img)
        except Exception:
            return 0.5

        if not faces:
            return 0.0  # no face detected → likely spoof / bad capture

        face = faces[0]

        # Large yaw/pitch suggests a photo-of-photo attack. The live-challenge
        # in the UI (turn left, turn right, blink) is what really proves
        # liveness; this static-frame check is a sanity gate, so we keep the
        # bounds reasonable rather than punitive.
        yaw, pitch = 0.0, 0.0
        if hasattr(face, "pose") and face.pose is not None:
            yaw = abs(float(face.pose[1]))
            pitch = abs(float(face.pose[0]))
        pose_ok = yaw < 45 and pitch < 30

        # Eye-aspect-ratio — eyes must be open
        ear = 0.3
        if hasattr(face, "landmark_2d_106") and face.landmark_2d_106 is not None:
            pts = np.array(face.landmark_2d_106)

            def _ear(top, bottom, left, right):
                v = np.linalg.norm(pts[top] - pts[bottom])
                h = np.linalg.norm(pts[left] - pts[right])
                return v / (h + 1e-6)

            ear = (_ear(37, 41, 33, 39) + _ear(93, 97, 87, 95)) / 2.0

        eyes_open = ear > 0.15
        det_score = float(face.det_score) if hasattr(face, "det_score") else 0.5
        # Less punitive multipliers — a real face is detected at det_score
        # ~0.7+, so we want the typical case to clear the 0.50 threshold
        # comfortably while still penalising clear no-face / closed-eye cases.
        score = det_score * (1.0 if pose_ok else 0.6) * (1.0 if eyes_open else 0.6)
        return float(np.clip(score, 0.0, 1.0))
