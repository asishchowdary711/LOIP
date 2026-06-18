"""ELA (Error Level Analysis) + EXIF metadata tampering detector.

ELA detects image manipulation by re-saving at reduced JPEG quality and
measuring pixel-level differences. EXIF inspection looks for editing-software
markers and metadata inconsistencies.

overall_tampered is True only when BOTH ela_anomaly AND exif_anomaly fire,
preventing single-signal false positives from noisy scans.
"""

from __future__ import annotations

import io
import logging

import numpy as np

from .schemas import QRTampering

logger = logging.getLogger(__name__)

_DEFAULT_ELA_THRESHOLD = 0.15
_DEFAULT_EDITING_KEYWORDS = [
    "photoshop", "gimp", "illustrator", "lightroom",
    "affinity", "pixelmator", "acrobat", "inkscape",
]


class TamperingDetector:
    """Stateless ELA + EXIF tampering analyser for document images."""

    def __init__(
        self,
        mock_mode: bool = True,
        ela_threshold: float = _DEFAULT_ELA_THRESHOLD,
        exif_editing_software_keywords: list[str] | None = None,
    ) -> None:
        self.mock_mode = mock_mode
        self.ela_threshold = ela_threshold
        self.editing_keywords = exif_editing_software_keywords or _DEFAULT_EDITING_KEYWORDS

    def analyze(
        self,
        image: np.ndarray,
        source_image_bytes: bytes | None = None,
    ) -> QRTampering:
        if self.mock_mode:
            return QRTampering(
                ela_score=0.04,
                ela_anomaly=False,
                ela_threshold=self.ela_threshold,
                exif_anomalies=[],
                exif_anomaly=False,
                overall_tampered=False,
            )

        ela_score, ela_anomaly = self._run_ela(image)
        exif_anomalies, exif_anomaly = self._run_exif(source_image_bytes, image)

        return QRTampering(
            ela_score=ela_score,
            ela_anomaly=ela_anomaly,
            ela_threshold=self.ela_threshold,
            exif_anomalies=exif_anomalies,
            exif_anomaly=exif_anomaly,
            overall_tampered=ela_anomaly and exif_anomaly,
        )

    def _run_ela(self, image: np.ndarray) -> tuple[float, bool]:
        try:
            from PIL import Image

            pil_img = Image.fromarray(image[..., ::-1])  # BGR → RGB

            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=75)
            buf.seek(0)
            reloaded = Image.open(buf).convert("RGB")

            orig_arr = np.array(pil_img, dtype=np.float32)
            relo_arr = np.array(reloaded, dtype=np.float32)

            ela_score = float(np.mean(np.abs(orig_arr - relo_arr)) / 255.0)
            return ela_score, ela_score > self.ela_threshold
        except Exception as exc:
            logger.warning("ELA analysis failed: %s", exc)
            return 0.0, False

    def _run_exif(
        self,
        image_bytes: bytes | None,
        image: np.ndarray,
    ) -> tuple[list[str], bool]:
        anomalies: list[str] = []
        try:
            from PIL import Image
            from PIL.ExifTags import TAGS

            if image_bytes is not None:
                pil_img = Image.open(io.BytesIO(image_bytes))
            else:
                pil_img = Image.fromarray(image[..., ::-1])

            exif_data = pil_img._getexif() if hasattr(pil_img, "_getexif") else None  # noqa: SLF001
            if not exif_data:
                return anomalies, False

            named: dict[str, object] = {TAGS.get(k, k): v for k, v in exif_data.items()}

            # Check editing software keywords
            for tag in ("Software", "ProcessingSoftware", "ImageDescription"):
                val = str(named.get(tag, "")).lower()
                for kw in self.editing_keywords:
                    if kw in val:
                        anomalies.append(f"editing_software:{named.get(tag)}")
                        break

            # GPS strip indicator (GPS present in one tag group but empty)
            if "GPSInfo" in named and not named["GPSInfo"]:
                anomalies.append("gps_data_stripped")

            # ModifyDate vs DateTimeOriginal discrepancy > 60s
            modify = str(named.get("DateTime", ""))
            original = str(named.get("DateTimeOriginal", ""))
            if modify and original and modify != original:
                anomalies.append(f"modify_date_differs_from_original:{modify}")

            # Dimension mismatch
            xdim = named.get("ExifImageWidth") or named.get("PixelXDimension")
            ydim = named.get("ExifImageHeight") or named.get("PixelYDimension")
            if xdim and ydim:
                h, w = image.shape[:2]
                if abs(int(xdim) - w) > 2 or abs(int(ydim) - h) > 2:
                    anomalies.append(f"dimension_mismatch:exif={xdim}x{ydim},actual={w}x{h}")

        except Exception as exc:
            logger.warning("EXIF analysis failed: %s", exc)

        return anomalies, len(anomalies) > 0
