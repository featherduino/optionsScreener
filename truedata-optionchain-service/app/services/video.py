"""Utility helpers to stitch images into an MP4 clip."""

from __future__ import annotations

import base64
import binascii
import io
import os
import shutil
import subprocess
import tempfile
from typing import Any, Iterable

from PIL import Image


class VideoGenerationError(RuntimeError):
    """Raised when ffmpeg fails to compose the frames."""


def _ensure_dir() -> str:
    return tempfile.mkdtemp(prefix="video-gen-")


def _extract_b64_source(frame: Any) -> str:
    if isinstance(frame, str):
        return frame
    if isinstance(frame, dict):
        for key in ("data", "base64", "b64"):
            if isinstance(frame.get(key), str):
                return frame[key]
        binary = frame.get("binary")
        if isinstance(binary, dict):
            # Common n8n style payloads: binary.data or binary.data.data
            direct = binary.get("data")
            if isinstance(direct, str):
                return direct
            if isinstance(direct, dict):
                nested = direct.get("data") or direct.get("base64")
                if isinstance(nested, str):
                    return nested
        content = frame.get("content")
        if isinstance(content, str):
            return content
    raise ValueError("Frame payload must be a base64 string or object with data/base64 field.")


def _decode_image(frame: Any, idx: int) -> Image.Image:
    """Decode base64 payloads that may include data URLs and whitespace."""
    raw_str = _extract_b64_source(frame)
    if "," in raw_str and raw_str.split(",", 1)[0].startswith("data:"):
        raw_str = raw_str.split(",", 1)[1]
    cleaned = "".join(raw_str.strip().split())
    # Pad base64 if users trimmed padding characters.
    padding = len(cleaned) % 4
    if padding:
        cleaned += "=" * (4 - padding)
    try:
        raw = base64.b64decode(cleaned, validate=False)
    except binascii.Error as exc:
        raise ValueError(f"Frame index {idx} is not valid base64: {exc}") from exc
    return Image.open(io.BytesIO(raw))


def build_video_from_base64_images(
    frames: Iterable[Any],
    width: int = 1920,
    height: int = 1080,
    seconds_per_frame: float = 3.0,
) -> tuple[bytes, dict]:
    """
    Convert provided base64 frames into a single MP4 clip.

    Returns the video bytes plus metadata.
    """
    if seconds_per_frame <= 0:
        raise ValueError("seconds_per_frame must be positive")

    items = list(frames or [])
    if not items:
        raise ValueError("Provide at least one frame")

    temp_dir = _ensure_dir()
    video_path = os.path.join(temp_dir, "output.mp4")
    try:
        # Normalize each frame to requested resolution.
        for idx, frame in enumerate(items):
            image = _decode_image(frame, idx).convert("RGB")
            canvas = Image.new("RGB", (width, height), "black")
            resized = image.resize((width, height), Image.LANCZOS)
            canvas.paste(resized, (0, 0))
            frame_path = os.path.join(temp_dir, f"frame_{idx:04d}.png")
            canvas.save(frame_path, format="PNG")

        frame_rate = 1.0 / seconds_per_frame
        cmd = [
            "ffmpeg",
            "-y",
            "-framerate",
            f"{frame_rate}",
            "-i",
            os.path.join(temp_dir, "frame_%04d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-crf",
            "23",
            video_path,
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise VideoGenerationError(getattr(exc, "stderr", b"").decode() or str(exc)) from exc

        with open(video_path, "rb") as fh:
            payload = fh.read()
        metadata = {
            "frame_count": len(items),
            "duration_seconds": len(items) * seconds_per_frame,
            "width": width,
            "height": height,
        }
        return payload, metadata
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
