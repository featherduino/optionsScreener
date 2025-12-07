"""Google Drive upload helper for chart endpoints."""

from __future__ import annotations

import json
import os
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
_drive_service = None


class DriveConfigurationError(RuntimeError):
    """Raised when Google Drive configuration variables are missing or invalid."""


class DriveUploadError(RuntimeError):
    """Raised when an upload to Google Drive fails."""


def _load_service_account_info() -> dict[str, Any]:
    raw = os.getenv("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise DriveConfigurationError("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON is not configured")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DriveConfigurationError("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON is not valid JSON") from exc


def _get_drive_service():
    global _drive_service
    if _drive_service is not None:
        return _drive_service

    info = _load_service_account_info()
    try:
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        _drive_service = build("drive", "v3", credentials=creds)
        return _drive_service
    except Exception as exc:
        raise DriveConfigurationError(f"Failed to initialize Google Drive client: {exc}") from exc


def upload_png(filename: str, payload: bytes) -> dict[str, Any]:
    """Upload PNG bytes to the configured Drive folder."""
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    if not folder_id:
        raise DriveConfigurationError("GOOGLE_DRIVE_FOLDER_ID is not configured")

    service = _get_drive_service()
    metadata = {
        "name": filename,
        "mimeType": "image/png",
        "parents": [folder_id],
    }
    media = MediaInMemoryUpload(payload, mimetype="image/png", resumable=False)
    try:
        result = (
            service.files()
            .create(body=metadata, media_body=media, fields="id, name, webViewLink, webContentLink")
            .execute()
        )
        return {
            "id": result.get("id"),
            "name": result.get("name"),
            "webViewLink": result.get("webViewLink"),
            "webContentLink": result.get("webContentLink"),
        }
    except Exception as exc:
        raise DriveUploadError(f"Drive upload failed: {exc}") from exc
