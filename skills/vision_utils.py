import cv2
import numpy as np
import os
from typing import Generator, Tuple

def _compute_dhash(image: np.ndarray, hash_size: int = 8) -> int:
    """
    Compute a difference hash (dHash) of an image.
    1. Convert to grayscale.
    2. Resize to (hash_size + 1)x(hash_size).
    3. Compare adjacent pixels.
    """
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
        
    resized = cv2.resize(gray, (hash_size + 1, hash_size))
    diff = resized[:, 1:] > resized[:, :-1]
    
    return sum([2 ** i for (i, v) in enumerate(diff.flatten()) if v])

def _hamming_distance(h1: int, h2: int) -> int:
    """Calculate the Hamming distance between two integers."""
    return bin(h1 ^ h2).count("1")

def extract_potential_slides(video_path: str, sample_rate: float = 1.0, similarity_threshold: float = 0.95) -> Generator[Tuple[float, np.ndarray], None, None]:
    """
    Samples frames from the video.
    Uses dHash to skip frames that are highly similar to the last yielded frame.
    This prevents running OCR on identical frames.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
        
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {video_path}")
        
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0
        
    frame_interval = max(1, int(fps / sample_rate))
    frame_count = 0
    
    last_hash = None
    hash_size = 8
    max_diff = (hash_size * hash_size) * (1.0 - similarity_threshold)
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        if frame_count % frame_interval == 0:
            current_hash = _compute_dhash(frame, hash_size)
            
            should_yield = False
            if last_hash is None:
                should_yield = True
            else:
                dist = _hamming_distance(last_hash, current_hash)
                if dist > max_diff:
                    should_yield = True
                    
            if should_yield:
                last_hash = current_hash
                timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
                yield timestamp_ms, frame
            
        frame_count += 1
        
    cap.release()

def extract_frames(video_path: str, output_dir: str, sample_rate: float = 1.0, diff_threshold: float = 10.0) -> int:
    """
    Extracts frames from the video and saves them as images.
    """
    os.makedirs(output_dir, exist_ok=True)
    count = 0
    
    for timestamp_ms, frame in extract_potential_slides(video_path, sample_rate=sample_rate):
        frame_path = os.path.join(output_dir, f"frame_{count:05d}.jpg")
        cv2.imwrite(frame_path, frame)
        count += 1
        
    return count
