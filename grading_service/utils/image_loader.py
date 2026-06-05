import httpx
import base64
from typing import Tuple


async def load_image_as_base64(image_url: str) -> Tuple[str, str]:
    """
    Fetches image from a URL and returns (base64_string, media_type).
    Used by handwritten and diagram agents.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(image_url, timeout=15.0)
        response.raise_for_status()

    content_type = response.headers.get("content-type", "image/png")
    media_type = content_type.split(";")[0].strip()

    base64_data = base64.b64encode(response.content).decode("utf-8")
    return base64_data, media_type
