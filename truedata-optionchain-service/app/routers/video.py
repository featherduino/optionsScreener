from __future__ import annotations

import base64

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.services.drive import (
    DriveConfigurationError,
    DriveUploadError,
    upload_mp4,
)
from app.services.video import VideoGenerationError, build_video_from_base64_images


router = APIRouter(prefix="/media", tags=["media"])


class VideoRequest(BaseModel):
    frames: list[Any] = Field(..., description="Base64 images or objects with data/base64 fields.")
    width: int = Field(1920, ge=16, le=3840)
    height: int = Field(1080, ge=16, le=2160)
    seconds_per_frame: float = Field(3.0, gt=0)


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
