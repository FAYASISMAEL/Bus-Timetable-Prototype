import warnings
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from backend.utils.errors import AppError

MAX_PIXELS = 40_000_000
MAX_SIDE = 3200
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def read_image(path: Path) -> np.ndarray:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.format not in {"JPEG", "PNG"}:
                    raise AppError(415, "unsupported_image", "Only JPEG and PNG images are supported.")
                if image.width * image.height > MAX_PIXELS or min(image.size) < 20:
                    raise AppError(422, "image_dimensions", "Image dimensions must be at least 20 pixels and at most 40 megapixels.")
                image.load()
                image = ImageOps.exif_transpose(image)
                if "A" in image.getbands() or "transparency" in image.info:
                    rgba = image.convert("RGBA")
                    background = Image.new("RGBA", rgba.size, "white")
                    image = Image.alpha_composite(background, rgba)
                return cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    except AppError:
        raise
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise AppError(422, "unreadable_image", "Could not read this image. Upload a valid JPEG or PNG under 40 megapixels.") from exc


def resize_image(image: np.ndarray) -> np.ndarray:
    scale = min(1.0, MAX_SIDE / max(image.shape[:2]))
    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else image


def correct_perspective(image: np.ndarray) -> tuple[np.ndarray, bool]:
    """Only rectify an unambiguous, nearly full-frame document quadrilateral."""
    height, width = image.shape[:2]
    edges = cv2.Canny(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 60, 180)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:3]:
        if cv2.contourArea(contour) < height * width * 0.70:
            continue
        polygon = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        points = polygon.reshape(4, 2).astype(np.float32)
        sums, differences = points.sum(axis=1), np.diff(points, axis=1).ravel()
        ordered = np.array([points[sums.argmin()], points[differences.argmin()],
                            points[sums.argmax()], points[differences.argmax()]], dtype=np.float32)
        corners = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)
        distances = np.linalg.norm((ordered - corners) / [width, height], axis=1)
        if len(np.unique(ordered, axis=0)) != 4 or distances.max() > 0.18 or distances.max() < 0.025:
            continue
        matrix = cv2.getPerspectiveTransform(ordered, corners)
        return cv2.warpPerspective(image, matrix, (width, height), borderValue=(255, 255, 255)), True
    return image, False


def deskew(gray: np.ndarray) -> tuple[np.ndarray, float]:
    edges = cv2.Canny(gray, 70, 180)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 1800, threshold=80,
                            minLineLength=max(80, gray.shape[1] // 5), maxLineGap=15)
    angles = []
    if lines is not None:
        for x1, y1, x2, y2 in lines[:, 0]:
            angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
            if abs(angle) < 7:
                angles.append(angle)
    if len(angles) < 3 or np.std(angles) > 1.5:
        return gray, 0.0
    angle = float(np.median(angles))
    if abs(angle) < 0.25:
        return gray, 0.0
    height, width = gray.shape
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1)
    # Expand the canvas so rotated corner text is never clipped.
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_width, new_height = int(height * sin + width * cos), int(height * cos + width * sin)
    matrix[0, 2] += (new_width - width) / 2
    matrix[1, 2] += (new_height - height) / 2
    return cv2.warpAffine(gray, matrix, (new_width, new_height), flags=cv2.INTER_CUBIC, borderValue=255), angle


def preprocess_image(image: np.ndarray) -> tuple[np.ndarray, dict]:
    image = resize_image(image)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Clean pages need only grayscale. Deskew acts only on measured, consistent tilt.
    if np.percentile(gray, 95) - np.percentile(gray, 5) < 60 and gray.std() > 5:
        gray = cv2.createCLAHE(clipLimit=1.2, tileGridSize=(8, 8)).apply(gray)
    processed, angle = deskew(gray)
    return processed, {"width": processed.shape[1], "height": processed.shape[0],
                       "deskew_degrees": round(angle, 2), "perspective_corrected": False}


def remove_table_grid(gray: np.ndarray) -> tuple[np.ndarray, bool]:
    """Mask only a detected grid of long straight rules, leaving grayscale glyphs intact."""
    _, ink = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)
    horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                                 cv2.getStructuringElement(cv2.MORPH_RECT, (max(40, gray.shape[1] // 4), 1)))
    vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                               cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(40, gray.shape[0] // 5))))
    h_count = cv2.connectedComponents(horizontal)[0] - 1
    v_count = cv2.connectedComponents(vertical)[0] - 1
    if h_count < 2 or v_count < 2:
        return gray, False
    mask = cv2.dilate(cv2.bitwise_or(horizontal, vertical), np.ones((3, 3), np.uint8))
    cleaned = gray.copy()
    cleaned[mask > 0] = 255
    return cleaned, True
