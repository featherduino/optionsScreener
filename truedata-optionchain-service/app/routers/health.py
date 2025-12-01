from fastapi import APIRouter
from app.td_client import td_client

router = APIRouter(prefix="/health", tags=["health"])

@router.get("/")
def health():
    return {"status": "ok"}


@router.get("/auth")
def auth_health():
    """
    Expose token freshness without leaking the token itself.
    """
    return td_client.token_status()
