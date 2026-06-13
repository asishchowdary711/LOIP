"""Image preprocessing pipeline for scanned Indian documents.

5-step pipeline: deskew → deblur → adaptive threshold → denoise → border crop.
Operates on numpy arrays (H, W, C) BGR format as used by OpenCV.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    pass

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


def _require_cv2() -> None:
    if cv2 is None:
        raise ImportError(
            "opencv-python is required for preprocessing. "
            "Install with: pip install opencv-python-headless"
        )


def deskew(image: np.ndarray, max_angle: float = 15.0) -> np.ndarray:
    """Correct rotation up to ±max_angle degrees using Hough line detection."""
    _require_cv2()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=50, maxLineGap=10)
    if lines is None:
        return image

    angles: list[float] = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        dx, dy = x2 - x1, y2 - y1
        if abs(dx) < 1:
            continue
        angle = math.degrees(math.atan2(dy, dx))
        if abs(angle) <= max_angle:
            angles.append(angle)

    if not angles:
        return image

    median_angle = float(np.median(angles))
    if abs(median_angle) < 0.3:
        return image

    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    rotation_matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    return cv2.warpAffine(image, rotation_matrix, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def deblur(image: np.ndarray, kernel_size: int = 3) -> np.ndarray:
    """Sharpen via Laplacian-based unsharp masking."""
    _require_cv2()
    blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=3)
    return cv2.addWeighted(image, 1.5, blurred, -0.5, 0)


def adaptive_threshold(image: np.ndarray, block_size: int = 25, c: int = 10) -> np.ndarray:
    """Sauvola-style adaptive thresholding for uneven lighting.

    Returns a 3-channel image so downstream models get consistent input.
    """
    _require_cv2()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_size, c
    )
    return cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)


def denoise(image: np.ndarray, d: int = 9, sigma_color: float = 75, sigma_space: float = 75) -> np.ndarray:
    """Bilateral filter — reduces noise while preserving edges."""
    _require_cv2()
    return cv2.bilateralFilter(image, d, sigma_color, sigma_space)


def crop_borders(image: np.ndarray, border_pct: float = 0.02) -> np.ndarray:
    """Remove scan borders by trimming a percentage from each edge."""
    h, w = image.shape[:2]
    bh, bw = int(h * border_pct), int(w * border_pct)
    if bh * 2 >= h or bw * 2 >= w:
        return image
    return image[bh : h - bh, bw : w - bw]


def preprocess_image(
    image: np.ndarray,
    *,
    do_deskew: bool = True,
    do_deblur: bool = True,
    do_threshold: bool = False,
    do_denoise: bool = True,
    do_crop: bool = True,
) -> np.ndarray:
    """Full preprocessing pipeline.

    Threshold is off by default — useful for OCR on degraded scans but
    destroys color info needed by LayoutLMv3 classification.
    """
    result = image.copy()
    if do_deskew:
        result = deskew(result)
    if do_deblur:
        result = deblur(result)
    if do_threshold:
        result = adaptive_threshold(result)
    if do_denoise:
        result = denoise(result)
    if do_crop:
        result = crop_borders(result)
    return result
