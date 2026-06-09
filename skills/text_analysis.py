"""
text_analysis.py — V2.4 Multi-Scenario Slide OCR Pipeline

Supported scenarios (auto-detected):
  A) screen_record  — Direct screen recording (OBS, SnagIt, Windows capture)
     Frame IS the screen. High resolution, uniform lighting, UI chrome present.
  B) camera_screen  — Phone/camera filming a laptop/monitor screen
     Rectangular bright region inside a darker ambient frame.
  C) projection     — Camera filming a projector on a wall/whiteboard
     Trapezoidal bright region, perspective distortion, uneven illumination.

Pipeline per scenario:
  1. Scenario classification  → classify_scenario()
  2. Region extraction        → scenario-specific strategy chain
  3. UI chrome removal        → _remove_ui_chrome() (all scenarios)
  4. Illumination normaliz.   → _normalize_illumination() (projection/camera)
  5. Multi-attempt OCR        → _multi_attempt_ocr() (4 preprocessing stacks)
  6. Post-processing          → _filter_ui_text() (remove toolbar artefacts)
"""

import cv2
import re
import numpy as np
import easyocr
import json
import os
import difflib
import base64
from typing import List, Dict, Optional, Iterator, Tuple, Any

_reader = None


def frame_to_base64(frame: np.ndarray) -> str:
    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return "data:image/jpeg;base64," + base64.b64encode(buffer).decode('utf-8')


def get_reader() -> easyocr.Reader:
    global _reader
    if _reader is None:
        import sys
        if hasattr(sys.stdout, 'reconfigure'):
            try:
                sys.stdout.reconfigure(encoding='utf-8')
            except Exception:
                pass
        _reader = easyocr.Reader(['en', 'tr'])
    return _reader


# ── Utility ───────────────────────────────────────────────────────────────────

def _order_points(pts: np.ndarray) -> np.ndarray:
    """Return 4 pts as [top-left, top-right, bottom-right, bottom-left]."""
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def _warp_quad(frame: np.ndarray, approx: np.ndarray) -> Optional[np.ndarray]:
    """Perspective-warp a 4-corner polygon to a flat rectangle."""
    pts = approx.reshape(4, 2).astype(np.float32)
    rect = _order_points(pts)
    tl, tr, br, bl = rect
    w = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    h = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    if w < 80 or h < 60:
        return None
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(frame, M, (w, h))


# ── Step 1: Scenario Classification ──────────────────────────────────────────

def _classify_scenario(frame: np.ndarray) -> str:
    """
    Classify the input frame into one of three OCR scenarios:
      'screen_record'  — direct screen capture, frame IS the screen
      'camera_screen'  — camera filming a monitor/laptop screen
      'projection'     — camera filming a projected image on wall/whiteboard

    Decision tree based on:
      - Edge density at frame borders (camera footage has more edge noise at borders)
      - Ambient dark region ratio (camera footage has dark surroundings)
      - Brightness uniformity (screen recordings are very uniform)
      - Presence of a well-defined quad contour (projection/camera-screen)
    """
    fh, fw = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # ── Feature 1: border darkness ─────────────────────────────────────────
    # Camera shots have dark borders (desk, room). Screen recordings don't.
    border_w = max(20, int(fw * 0.06))
    border_h = max(20, int(fh * 0.06))
    top_strip    = gray[:border_h, :]
    bottom_strip = gray[fh - border_h:, :]
    left_strip   = gray[:, :border_w]
    right_strip  = gray[:, fw - border_w:]
    border_mean  = np.mean([top_strip.mean(), bottom_strip.mean(),
                            left_strip.mean(), right_strip.mean()])

    # ── Feature 2: overall brightness & uniformity ─────────────────────────
    overall_mean = float(np.mean(gray))
    overall_std  = float(np.std(gray))

    # ── Feature 3: dark pixel fraction (dark surrounding in camera shots) ──
    dark_fraction = float(np.sum(gray < 50) / (fh * fw))

    # ── Feature 4: quad detection probe ────────────────────────────────────
    # Check if there's a strong isolated quadrilateral (≤ 80% of frame area)
    has_isolated_quad = _probe_isolated_quad(gray, fh, fw)

    # ── Decision tree ──────────────────────────────────────────────────────
    # Screen recording: very bright, uniform, low dark fraction, border also bright
    if (overall_mean > 160 and overall_std < 70 and
            dark_fraction < 0.05 and border_mean > 120):
        return "screen_record"

    # Projection or camera-screen: there's an isolated quad in a darker frame
    if has_isolated_quad and dark_fraction > 0.08:
        # Projection tends to have more perspective distortion and lower uniformity
        # Camera-screen: usually higher overall brightness even outside the screen
        if overall_std > 60 or border_mean < 80:
            return "projection"
        return "camera_screen"

    # If frame is moderately bright with some dark regions → camera_screen
    if border_mean < 100 and overall_mean > 80:
        return "camera_screen"

    # Default: treat as screen_record (safest fallback for edge cases)
    return "screen_record"


def _probe_isolated_quad(gray: np.ndarray, fh: int, fw: int) -> bool:
    """Quick check: does the frame contain a well-defined isolated quadrilateral?"""
    frame_area = fh * fw
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    edges = cv2.Canny(blur, 30, 100)
    kernel = np.ones((15, 15), np.uint8)
    dilated = cv2.dilate(edges, kernel)
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < frame_area * 0.08 or area > frame_area * 0.90:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.03 * peri, True)
        if len(approx) == 4:
            return True
    return False


# ── Region Detection: Screen Recording ───────────────────────────────────────

def _detect_screen_record_region(frame: np.ndarray) -> np.ndarray:
    """
    For direct screen recordings: locate the slide content area by finding
    the largest bright axis-aligned region, then aggressively strip UI chrome.

    Falls back to adaptive centre-crop if no distinct slide area found.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    fh, fw = gray.shape
    frame_area = fh * fw

    # Bright content: slides are typically > 175 brightness
    _, thresh = cv2.threshold(gray, 175, 255, cv2.THRESH_BINARY)
    kernel = np.ones((30, 30), np.uint8)
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best_crop, best_area = None, 0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < frame_area * 0.08 or area > frame_area * 0.96:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        ratio = w / h if h > 0 else 0
        # Slide aspect ratio guard: 4:3 (1.33) to 16:9 (1.78), give some slack
        if not (0.7 <= ratio <= 3.2):
            continue
        if area > best_area:
            best_area = area
            best_crop = frame[max(0, y - 4):min(fh, y + h + 4),
                               max(0, x - 4):min(fw, x + w + 4)]

    if best_crop is not None and best_crop.size > 0:
        return _remove_ui_chrome(best_crop)

    # Fallback: aggressive adaptive centre-crop
    return _adaptive_centre_crop(frame)


# ── Region Detection: Camera → Screen ────────────────────────────────────────

def _detect_camera_screen_region(frame: np.ndarray) -> np.ndarray:
    """
    For camera shots of laptop/monitor screens:
    1. Try quad detection (mild parameters — screen is usually rectangular)
    2. Fall back to bright-rect detection
    3. Fall back to centre-crop
    """
    # Pass 1: Try quadrilateral (screen may have slight perspective)
    result = _try_quad_detection(frame, area_min=0.08, area_max=0.92,
                                  epsilon_factor=0.02)
    if result is not None:
        fh, fw = frame.shape[:2]
        rh, rw = result.shape[:2]
        if rh * rw >= fh * fw * 0.08:
            return _remove_ui_chrome(result)

    # Pass 2: Bright-rect (monitor is bright rectangular blob)
    result = _try_bright_rect(frame, brightness_threshold=160, area_min=0.08)
    if result is not None and result.size > 0:
        return _remove_ui_chrome(result)

    # Pass 3: Centre-crop as last resort
    return _remove_ui_chrome(_adaptive_centre_crop(frame))


# ── Region Detection: Camera → Projection ────────────────────────────────────

def _detect_projection_region(frame: np.ndarray) -> np.ndarray:
    """
    For camera shots of projected images on wall/whiteboard:
    1. Aggressive multi-scale Canny-based quad detection
    2. Fall back to bright-rect with lower threshold (projections are dimmer)
    3. Fall back to centre-crop

    After region extraction, apply illumination normalization to compensate
    for uneven projector light (brighter in centre, darker at edges).
    """
    # Pass 1: Canny-based aggressive quad detection
    result = _try_projection_quad(frame)
    if result is not None:
        return _remove_ui_chrome(result)

    # Pass 2: Bright-rect with lower threshold (projections can be dim: ~120)
    result = _try_bright_rect(frame, brightness_threshold=120, area_min=0.07)
    if result is not None and result.size > 0:
        return _remove_ui_chrome(result)

    # Pass 3: Adaptive centre-crop
    result = _adaptive_centre_crop(frame)
    return _remove_ui_chrome(result)


# ── Quad Detection Variants ───────────────────────────────────────────────────

def _try_quad_detection(frame: np.ndarray,
                         area_min: float = 0.08,
                         area_max: float = 0.95,
                         epsilon_factor: float = 0.02) -> Optional[np.ndarray]:
    """
    General-purpose quadrilateral detection using adaptive threshold.
    Parameters tunable per scenario.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    fh, fw = gray.shape
    frame_area = fh * fw

    smooth = cv2.bilateralFilter(gray, 9, 75, 75)
    thresh = cv2.adaptiveThreshold(smooth, 255,
                                   cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 51, -10)
    kernel = np.ones((20, 20), np.uint8)
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best, best_area = None, 0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < frame_area * area_min or area > frame_area * area_max:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon_factor * peri, True)
        if len(approx) == 4 and area > best_area:
            best, best_area = approx, area

    if best is not None:
        warped = _warp_quad(frame, best)
        if warped is not None:
            return warped
    return None


def _try_projection_quad(frame: np.ndarray) -> Optional[np.ndarray]:
    """
    Aggressive Canny-based quad detection optimised for projected screens:
    - Multiple Canny threshold levels
    - Larger morphological kernel (handles broken edges from uneven illumination)
    - Accepts trapezoids (4-6 corners after approximation, collapsed to 4)
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    fh, fw = gray.shape
    frame_area = fh * fw

    blur = cv2.GaussianBlur(gray, (7, 7), 0)

    best_warped = None
    best_area = 0

    # Try multiple Canny thresholds to handle varying contrast
    for low, high in [(20, 80), (30, 120), (50, 150)]:
        edges = cv2.Canny(blur, low, high)
        kernel = np.ones((25, 25), np.uint8)
        dilated = cv2.dilate(edges, kernel)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < frame_area * 0.07 or area > frame_area * 0.92:
                continue
            peri = cv2.arcLength(cnt, True)
            # Try epsilon from 1% to 5% — projection edges can be irregular
            for eps_f in [0.01, 0.02, 0.03, 0.05]:
                approx = cv2.approxPolyDP(cnt, eps_f * peri, True)
                n = len(approx)
                if 4 <= n <= 6:
                    # Collapse to convex hull with 4 corners
                    hull = cv2.convexHull(approx)
                    hull_approx = cv2.approxPolyDP(hull, 0.03 * cv2.arcLength(hull, True), True)
                    if len(hull_approx) == 4 and area > best_area:
                        warped = _warp_quad(frame, hull_approx)
                        if warped is not None:
                            best_area = area
                            best_warped = warped
                        break

    return best_warped


# ── Bright-rect detection (shared) ────────────────────────────────────────────

def _try_bright_rect(frame: np.ndarray,
                      brightness_threshold: int = 180,
                      area_min: float = 0.10) -> Optional[np.ndarray]:
    """
    Find the largest bright axis-aligned rectangle.
    brightness_threshold: lower for dim projectors, higher for screens.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    fh, fw = gray.shape
    frame_area = fh * fw

    _, thresh = cv2.threshold(gray, brightness_threshold, 255, cv2.THRESH_BINARY)
    kernel = np.ones((25, 25), np.uint8)
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best_crop, best_area = None, 0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < frame_area * area_min or area > frame_area * 0.96:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        ratio = w / h if h > 0 else 0
        if not (0.7 <= ratio <= 3.2):
            continue
        if area > best_area:
            best_area = area
            best_crop = frame[max(0, y - 5):min(fh, y + h + 5),
                               max(0, x - 5):min(fw, x + w + 5)]

    return best_crop


# ── Strategy 3: Adaptive centre-crop ─────────────────────────────────────────

def _adaptive_centre_crop(frame: np.ndarray) -> np.ndarray:
    """
    Heuristic crop removing UI chrome (toolbars, status bars, notes panels).
    Top 18% and bottom 22% excluded; left/right 3% margins removed.
    Refines to the vertical bright content band within that crop.
    """
    fh, fw = frame.shape[:2]
    top    = int(fh * 0.18)
    bottom = int(fh * 0.78)
    left   = int(fw * 0.03)
    right  = int(fw * 0.97)
    cropped = frame[top:bottom, left:right]

    gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
    row_means = np.mean(gray, axis=1)
    bright_rows = np.where(row_means > 150)[0]
    if len(bright_rows) > 20:
        r_top = max(0, bright_rows[0] - 5)
        r_bot = min(cropped.shape[0], bright_rows[-1] + 5)
        cropped = cropped[r_top:r_bot, :]

    return cropped


# ── Pass 2: UI Chrome Removal ─────────────────────────────────────────────────

def _remove_ui_chrome(region: np.ndarray, min_bright_fraction: float = 0.06) -> np.ndarray:
    """
    Scan horizontal brightness profile to strip dark UI chrome bands
    (toolbars, ribbon menus, status bars, taskbars) from top and bottom.
    Keeps only the largest contiguous bright band (the actual slide content).
    """
    if region is None or region.size == 0:
        return region

    rh, rw = region.shape[:2]
    if rh < 60 or rw < 80:
        return region

    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    row_means = np.mean(gray, axis=1)

    # Dynamic threshold: adapts to slide brightness (bright slides vs projections)
    threshold = np.percentile(row_means, 75) * 0.55
    threshold = max(threshold, 70.0)
    threshold = min(threshold, 185.0)

    is_bright = row_means >= threshold

    # Find the longest contiguous run of bright rows
    longest_start, longest_end, longest_len = 0, rh, 0
    cur_start = None

    for i, bright in enumerate(is_bright):
        if bright:
            if cur_start is None:
                cur_start = i
        else:
            if cur_start is not None:
                run_len = i - cur_start
                if run_len > longest_len:
                    longest_len = run_len
                    longest_start = cur_start
                    longest_end = i
                cur_start = None
    if cur_start is not None:
        run_len = rh - cur_start
        if run_len > longest_len:
            longest_len = run_len
            longest_start = cur_start
            longest_end = rh

    if longest_len < rh * min_bright_fraction:
        return region

    top_chrome    = longest_start
    bottom_chrome = rh - longest_end
    if top_chrome < rh * 0.03 and bottom_chrome < rh * 0.03:
        return region

    pad = max(3, int(rh * 0.01))
    y1 = max(0, longest_start - pad)
    y2 = min(rh, longest_end + pad)

    cropped = region[y1:y2, :]
    return cropped if cropped.size > 0 else region


# ── Illumination Normalization (for projection/camera scenarios) ──────────────

def _normalize_illumination(region: np.ndarray, scenario: str) -> np.ndarray:
    """
    Two-Path Preprocessing based on scenario.
    Path A (projection): Blur + Divide Normalization + CLAHE (16x16)
    Path B (camera_screen / screen_record): Bypass Divide. Grayscale -> CLAHE (8x8) -> BGR
    """
    if region is None or region.size == 0:
        return region

    if scenario == "screen_record":
        return region

    rh, rw = region.shape[:2]
    if rh < 60 or rw < 80:
        return region

    if scenario == "projection":
        # Path A: Blur + Divide Normalization
        img_float = region.astype(np.float32)
        blur_ksize = (max(51, (rw // 4) | 1), max(51, (rh // 4) | 1))
        illumination = cv2.GaussianBlur(img_float, blur_ksize, 0)

        # Divide normalization: flatten the gradient
        normalized = img_float / (illumination + 1.0) * 128.0
        normalized = np.clip(normalized, 0, 255).astype(np.uint8)

        # CLAHE with larger tile for wide illumination variation
        lab = cv2.cvtColor(normalized, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(16, 16))
        l_ch = clahe.apply(l_ch)
        normalized = cv2.cvtColor(cv2.merge([l_ch, a_ch, b_ch]), cv2.COLOR_LAB2BGR)
        return normalized

    else:
        # Path B: camera_screen (and fallback)
        # Bypass Divide Normalization.
        # Apply localized contrast boost using CLAHE (8x8 grid) on Grayscale.
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray_clahe = clahe.apply(gray)
        
        # Convert back to BGR so downstream OCR multi-stacks (which expect BGR) don't crash
        bgr_clahe = cv2.cvtColor(gray_clahe, cv2.COLOR_GRAY2BGR)
        return bgr_clahe


# ── Public: Detect Slide Region (scenario-aware) ──────────────────────────────

def detect_slide_region(frame: np.ndarray) -> Tuple[np.ndarray, str]:
    """
    Classify the frame scenario, then apply the appropriate region extraction.
    Returns (region, scenario_label) for downstream processing.
    """
    scenario = _classify_scenario(frame)

    if scenario == "screen_record":
        region = _detect_screen_record_region(frame)
    elif scenario == "camera_screen":
        region = _detect_camera_screen_region(frame)
    else:  # projection
        region = _detect_projection_region(frame)

    if region is None or region.size == 0:
        region = frame

    region = _normalize_illumination(region, scenario)

    return region, scenario


# ── Multi-Attempt OCR ─────────────────────────────────────────────────────────

def _upscale_if_needed(img: np.ndarray, min_width: int = 800) -> np.ndarray:
    """Upscale small images to improve OCR accuracy."""
    h, w = img.shape[:2]
    if w < min_width:
        scale = min_width / w
        img = cv2.resize(img, (int(w * scale), int(h * scale)),
                         interpolation=cv2.INTER_CUBIC)
    return img


def _sharpen(img: np.ndarray) -> np.ndarray:
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    return cv2.filter2D(img, -1, kernel)


def _multi_attempt_ocr(reader: easyocr.Reader,
                        region: np.ndarray,
                        scenario: str) -> str:
    """
    Run OCR with 4 different preprocessing stacks and return the best result
    (longest non-empty text, prioritising higher confidence).

    Stacks:
      1. Color → sharpen → upscale             (good for bright slides)
      2. CLAHE LAB → grayscale → upscale       (low-contrast / dim)
      3. Adaptive threshold binarization        (camera noise / grain)
      4. Otsu binarization (inverted if needed) (high-contrast projection text)
    """
    candidates: List[Tuple[str, float]] = []  # (text, score)

    region_up = _upscale_if_needed(region, min_width=900)

    # Helper to evaluate early exit
    def is_good_enough(text: str, conf: float) -> bool:
        return len(text.strip()) > 10 and conf > 0.45

    # ── Stack 1: Sharpened color ──────────────────────────────────────────
    try:
        s1 = _sharpen(region_up)
        results = reader.readtext(
            s1,
            mag_ratio=1.5,
            contrast_ths=0.1,
            adjust_contrast=0.5,
            text_threshold=0.65,
            low_text=0.35,
        )
        txt1 = "\n".join(r[1] for r in results)
        conf1 = float(np.mean([r[2] for r in results])) if results else 0.0
        if is_good_enough(txt1, conf1):
            return txt1.strip()
        candidates.append((txt1, conf1))
    except Exception:
        candidates.append(("", 0.0))

    # ── Stack 2: CLAHE + grayscale ────────────────────────────────────────
    try:
        lab = cv2.cvtColor(region_up, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        l_ch = clahe.apply(l_ch)
        enhanced = cv2.merge([l_ch, a_ch, b_ch])
        gray_s2 = cv2.cvtColor(enhanced, cv2.COLOR_LAB2GRAY)
        rgb_s2 = cv2.cvtColor(gray_s2, cv2.COLOR_GRAY2RGB)
        results = reader.readtext(
            rgb_s2,
            mag_ratio=1.8,
            contrast_ths=0.08,
            adjust_contrast=0.6,
            text_threshold=0.6,
            low_text=0.3,
        )
        txt2 = "\n".join(r[1] for r in results)
        conf2 = float(np.mean([r[2] for r in results])) if results else 0.0
        if is_good_enough(txt2, conf2):
            return txt2.strip()
        candidates.append((txt2, conf2))
    except Exception:
        candidates.append(("", 0.0))

    # ── Stack 3: Adaptive threshold (handles grain/noise in camera shots) ─
    try:
        gray_s3 = cv2.cvtColor(region_up, cv2.COLOR_BGR2GRAY)
        # Denoise first for camera footage
        if scenario in ("camera_screen", "projection"):
            gray_s3 = cv2.fastNlMeansDenoising(gray_s3, h=10)
        binary_s3 = cv2.adaptiveThreshold(
            gray_s3, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 51, 8
        )
        rgb_s3 = cv2.cvtColor(binary_s3, cv2.COLOR_GRAY2RGB)
        results = reader.readtext(
            rgb_s3,
            mag_ratio=1.5,
            contrast_ths=0.05,
            adjust_contrast=0.7,
            text_threshold=0.55,
            low_text=0.25,
        )
        txt3 = "\n".join(r[1] for r in results)
        conf3 = float(np.mean([r[2] for r in results])) if results else 0.0
        if is_good_enough(txt3, conf3):
            return txt3.strip()
        candidates.append((txt3, conf3))
    except Exception:
        candidates.append(("", 0.0))

    # ── Stack 4: Otsu binarization ─────────────────────────────────────────
    try:
        gray_s4 = cv2.cvtColor(region_up, cv2.COLOR_BGR2GRAY)
        _, binary_s4 = cv2.threshold(gray_s4, 0, 255,
                                      cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        # If text is white-on-dark, invert
        if np.mean(binary_s4) < 127:
            binary_s4 = cv2.bitwise_not(binary_s4)
        rgb_s4 = cv2.cvtColor(binary_s4, cv2.COLOR_GRAY2RGB)
        results = reader.readtext(
            rgb_s4,
            mag_ratio=1.5,
            contrast_ths=0.05,
            adjust_contrast=0.8,
            text_threshold=0.6,
            low_text=0.3,
        )
        txt4 = "\n".join(r[1] for r in results)
        conf4 = float(np.mean([r[2] for r in results])) if results else 0.0
        candidates.append((txt4, conf4))
    except Exception:
        candidates.append(("", 0.0))

    # ── Select best result ─────────────────────────────────────────────────
    # Score = character count * confidence. Prioritise longer + confident.
    def score(c: Tuple[str, float]) -> float:
        text, conf = c
        stripped = text.strip()
        if not stripped:
            return 0.0
        return len(stripped) * max(conf, 0.3)  # floor conf at 0.3 to avoid penalising

    best_text, _ = max(candidates, key=score, default=("", 0.0))
    return best_text.strip()


# ── Post-processing: Filter UI Text Artefacts ─────────────────────────────────

# Patterns that indicate OCR has read UI chrome rather than slide content
_UI_PATTERNS = [
    r'^\d{1,2}:\d{2}(?:\s*[AP]M)?$',          # Clock: 12:34 PM
    r'^\d{1,3}%$',                              # Percentage: 85%
    r'^(?:File|Edit|View|Insert|Format|Tools|'
    r'Help|Home|Design|Transitions|Animations|'
    r'Slide Show|Review|Draw|Undo|Redo)$',      # Menu names (EN)
    r'^(?:Dosya|Düzen|Görünüm|Ekle|Biçim|'
    r'Araçlar|Yardım|Tasarım|Slayt Gösterisi|'
    r'İncele|Geri Al|Yinele)$',                 # Menu names (TR)
    r'^Slide \d+ of \d+$',                      # Slide counter
    r'^Slayt \d+$',                             # Turkish slide counter
    r'^\d+ / \d+$',                             # Page counter
    r'^(?:Normal|Outline View|Slide Sorter|'
    r'Notes Page|Reading View)$',               # View names
    r'^(?:Click to add|Tıklayın).*',            # Placeholder text
    r'.*Microsoft 365 Denemenizi Başlatın.*',   # Aggressive UI artifact filter
]
_UI_RE = [re.compile(p, re.IGNORECASE) for p in _UI_PATTERNS]


def _filter_ui_text(text: str) -> str:
    """
    Remove lines that look like OCR'd application UI chrome rather than
    slide content. Applies regex patterns for common UI artefacts and
    filters out suspiciously short isolated tokens.
    """
    if not text:
        return text

    lines = text.split('\n')
    filtered = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip very short lines (≤ 2 chars) that are almost always artefacts
        if len(stripped) <= 2:
            continue
        # Skip lines matching known UI patterns
        if any(pat.match(stripped) for pat in _UI_RE):
            continue
        filtered.append(stripped)

    return '\n'.join(filtered)


# ── Public API ────────────────────────────────────────────────────────────────

def extract_text_from_frame(frame: np.ndarray) -> dict:
    """
    Full V2.4 pipeline:
      1. Classify scenario (screen_record / camera_screen / projection)
      2. Extract slide region (scenario-specific strategy chain)
      3. UI chrome removal (brightness-band crop)
      4. Illumination normalization (projection/camera)
      5. Multi-attempt OCR (4 preprocessing stacks, best result)
      6. UI text filtering (remove toolbar artefacts from OCR output)

    Returns:
      {
        'text':        cleaned OCR text,
        'scenario':    detected scenario label,
        'original_b64': base64 JPEG of the raw input frame,
        'warped_b64':   base64 JPEG of the region sent to OCR
      }
    """
    reader = get_reader()

    # Steps 1–4: region extraction
    region, scenario = detect_slide_region(frame)

    # Step 5: multi-attempt OCR
    raw_text = _multi_attempt_ocr(reader, region, scenario)

    # Step 6: filter UI artefacts
    final_text = _filter_ui_text(raw_text)

    # Step 7: V3.5 Hybrid LLM Correction
    if len(final_text.strip()) > 10:
        try:
            from skills.ocr_correction import process_and_clean_ocr
            cleaned_dict = process_and_clean_ocr(final_text)
            final_text = json.dumps(cleaned_dict, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[!] Warning: OCR correction failed, falling back to raw OCR. Error: {e}")

    return {
        "text":         final_text,
        "scenario":     scenario,
        "original_b64": frame_to_base64(frame),
        "warped_b64":   frame_to_base64(region),
    }


def deduplicate_by_text(extracted_texts: List[str], new_text: str,
                         threshold: float) -> bool:
    """
    Returns True if new_text is a duplicate of any text in extracted_texts.
    Empty text is always treated as a duplicate (ignored).
    """
    if not new_text.strip():
        return True
    for text in extracted_texts:
        similarity = difflib.SequenceMatcher(None, text, new_text).ratio()
        if similarity >= threshold:
            return True
    return False


def analyze_slides(unique_slides_iter: Iterator[Tuple[float, np.ndarray]]
                   ) -> Iterator[Dict[str, Any]]:
    """Analyze unique slides and extract text and base64 debug images."""
    for timestamp_ms, frame in unique_slides_iter:
        result = extract_text_from_frame(frame)
        yield {
            "timestamp_ms":  timestamp_ms,
            "text":          result["text"],
            "scenario":      result.get("scenario", "unknown"),
            "original_b64":  result["original_b64"],
            "warped_b64":    result["warped_b64"],
        }


def extract_text_from_images(image_paths: List[str], output_json: str,
                              text_sim_thresh: float = 0.80) -> List[Dict[str, str]]:
    """
    Iterate over a list of image files, run the full OCR pipeline, and save
    extracted texts to a JSON file with text-based deduplication.
    """
    results = []
    saved_texts = []

    for path in image_paths:
        if not os.path.exists(path):
            continue
        frame = cv2.imread(path)
        if frame is None:
            continue

        result = extract_text_from_frame(frame)
        extracted_text = result["text"]

        if not deduplicate_by_text(saved_texts, extracted_text, text_sim_thresh):
            saved_texts.append(extracted_text)
            results.append({
                "image_path":     path,
                "extracted_text": extracted_text,
                "scenario":       result.get("scenario", "unknown"),
            })

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=4)

    return results
