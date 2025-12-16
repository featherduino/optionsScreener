from __future__ import annotations

import base64
import binascii
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.services.drive import (
    DriveConfigurationError,
    DriveUploadError,
    upload_mp4,
)
from app.services.video import (
    AudioMergeError,
    SpeechSynthesisError,
    VideoGenerationError,
    build_video_from_base64_images,
    merge_video_audio,
    synthesize_speech,
)


router = APIRouter(prefix="/media", tags=["media"])


class VideoRequest(BaseModel):
    frames: list[Any] = Field(..., description="Base64 images or objects with data/base64 fields.")
    width: int = Field(1080, ge=16, le=3840)
    height: int = Field(1920, ge=16, le=2160)
    seconds_per_frame: float = Field(3.0, gt=0)
    audio_base64: str | None = Field(
        None,
        description="Optional base64-encoded audio to merge into the video.",
    )
    caption_text: str | None = Field(
        None,
        description="Optional caption text to synthesize into audio when audio_base64 is not provided.",
    )
    tts_voice: str | None = Field(
        None,
        description="Optional voice identifier for text-to-speech (espeak voices).",
    )
    tts_rate: int | None = Field(
        None,
        ge=80,
        le=450,
        description="Optional speech rate (words per minute) for synthesized audio.",
    )


@router.post("/video-from-images")
def create_video(req: VideoRequest):
    try:
        video_bytes, meta = build_video_from_base64_images(
            req.frames,
            width=req.width,
            height=req.height,
            seconds_per_frame=req.seconds_per_frame,
        )
    except VideoGenerationError as exc:
        raise HTTPException(status_code=500, detail=f"Video generation failed: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audio_bytes: bytes | None = None
    if req.audio_base64:
        raw_audio = req.audio_base64.strip()
        if "," in raw_audio and raw_audio.split(",", 1)[0].startswith("data:"):
            raw_audio = raw_audio.split(",", 1)[1]
        padding = len(raw_audio) % 4
        if padding:
            raw_audio += "=" * (4 - padding)
        cleaned_audio = "".join(raw_audio.split())
        try:
            audio_bytes = base64.b64decode(cleaned_audio, validate=False)
        except binascii.Error as exc:
            raise HTTPException(status_code=400, detail=f"Invalid audio base64: {exc}") from exc

    elif req.caption_text:
        try:
            audio_bytes = synthesize_speech(
                req.caption_text,
                voice=req.tts_voice,
                rate=req.tts_rate,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SpeechSynthesisError as exc:
            raise HTTPException(status_code=500, detail=f"TTS failed: {exc}") from exc

    if audio_bytes:
        try:
            video_bytes = merge_video_audio(video_bytes, audio_bytes)
        except AudioMergeError as exc:
            raise HTTPException(status_code=500, detail=f"Audio merge failed: {exc}") from exc

    filename = "market_analysis.mp4"
    try:
        upload_result = upload_mp4(filename, video_bytes)
    except DriveConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except DriveUploadError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    payload = {
        "success": True,
        "frame_count": meta["frame_count"],
        "duration_seconds": meta["duration_seconds"],
        "width": meta["width"],
        "height": meta["height"],
        "video": {
            "url": upload_result["url"],
            "mime_type": "video/mp4",
            "filename": filename,
            "bucket": upload_result["bucket"],
            "key": upload_result["key"],
        },
    }
    return JSONResponse(payload)
