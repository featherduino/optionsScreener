"""Google Drive uploader for chart assets."""

from __future__ import annotations

import io
import json
import os
from dataclasses import dataclass

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload


DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class DriveConfigurationError(RuntimeError):
    """Raised when Drive integration is not configured."""


class DriveUploadError(RuntimeError):
    """Raised when uploading to Drive fails."""


_service = None


def _get_service():
    global _service
    if _service is not None:
        return _service

    creds_json = os.getenv("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON")
    if not creds_json:
        raise DriveConfigurationError("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON not configured")

    try:
        info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(info, scopes=DRIVE_SCOPES)
        _service = build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as exc:  # pragma: no cover - credentials parsing
        raise DriveConfigurationError(f"Invalid Drive credentials: {exc}") from exc
    return _service


def upload_png(name: str, data: bytes) -> dict:
    service = _get_service()
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    file_metadata = {"name": name}
    if folder_id:
        file_metadata["parents"] = [folder_id]

    media = MediaIoBaseUpload(io.BytesIO(data), mimetype="image/png")
    try:
        file = (
            service.files()
            .create(body=file_metadata, media_body=media, fields="id, webViewLink, webContentLink")
            .execute()
        )
        service.permissions().create(
            fileId=file["id"], body={"type": "anyone", "role": "reader"}
        ).execute()
    except Exception as exc:  # pragma: no cover - Drive API failure
        raise DriveUploadError(str(exc)) from exc

    file_id = file["id"]
    direct_link = f"https://drive.google.com/uc?id={file_id}"
    return {
        "file_id": file_id,
        "webViewLink": file.get("webViewLink"),
        "webContentLink": file.get("webContentLink"),
        "direct_link": direct_link,
    }

