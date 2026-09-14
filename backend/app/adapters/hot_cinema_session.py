"""Compatibility names for the shared Bigger Picture session implementation."""

from app.adapters.bigger_picture_session import (
    API_URL,
)
from app.adapters.bigger_picture_session import (
    BiggerPictureSession as HotCinemaSession,
)
from app.adapters.bigger_picture_session import (
    BiggerPictureSessionError as HotCinemaSessionError,
)

__all__ = ["API_URL", "HotCinemaSession", "HotCinemaSessionError"]
