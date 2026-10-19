"""Image utility functions for lfx package."""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

from lfx.log import logger
from lfx.services.deps import get_storage_service
from lfx.utils.async_helpers import run_until_complete
from lfx.utils.helpers import get_mime_type


def convert_image_to_base64(image_path: str | Path) -> str:
    """Convert an image file to a base64 encoded string.

    Handles both local files and S3 storage paths.

    Args:
        image_path: Path to the image file (local or S3 path like "flow_id/filename")

    Returns:
        Base64 encoded string of the image

    Raises:
        FileNotFoundError: If the image file doesn't exist
    """
    storage_service = get_storage_service()
    if storage_service:
        # Object-storage keys always use forward slashes.  Do not construct a
        # host ``Path`` before parsing: on Windows that turns ``flow/photo.png``
        # into ``flow\\photo.png`` and changes the object key.
        storage_path = image_path.as_posix() if isinstance(image_path, Path) else image_path
        flow_id, file_name = storage_service.parse_file_path(storage_path)
        try:
            file_content = run_until_complete(
                storage_service.get_file(flow_id=flow_id, file_name=file_name)  # type: ignore[call-arg]
            )
            return base64.b64encode(file_content).decode("utf-8")
        except Exception as e:
            logger.error(f"Error reading image file: {e}")
            raise

    # Fall back to local file access
    local_path = Path(image_path)
    if not local_path.exists():
        msg = f"Image file not found: {local_path}"
        raise FileNotFoundError(msg)

    with local_path.open("rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def create_data_url(image_path: str | Path, mime_type: str | None = None) -> str:
    """Create a data URL from an image file.

    Args:
        image_path: Path to the image file (local or S3 path like "flow_id/filename")
        mime_type: MIME type of the image. If None, will be auto-detected

    Returns:
        Data URL string in format: data:mime/type;base64,{base64_data}

    Raises:
        FileNotFoundError: If the image file doesn't exist
    """
    if mime_type is None:
        mime_type = get_mime_type(image_path)

    base64_data = convert_image_to_base64(image_path)
    return f"data:{mime_type};base64,{base64_data}"


@lru_cache(maxsize=50)
def create_image_content_dict(
    image_path: str | Path,
    mime_type: str | None = None,
    model_name: str | None = None,  # noqa: ARG001
) -> dict:
    """Create a content dictionary for multimodal inputs from an image file.

    Args:
        image_path: Path to the image file (local or S3 path like "flow_id/filename")
        mime_type: MIME type of the image. If None, will be auto-detected
        model_name: Optional model parameter (kept for backward compatibility, no longer used)

    Returns:
        Content dictionary with type and image_url fields

    Raises:
        FileNotFoundError: If the image file doesn't exist
    """
    data_url = create_data_url(image_path, mime_type)

    # Standard format for OpenAI, Anthropic, Gemini, and most providers
    # Format: {"type": "image_url", "image_url": {"url": "data:..."}}
    return {"type": "image_url", "image_url": {"url": data_url}}
