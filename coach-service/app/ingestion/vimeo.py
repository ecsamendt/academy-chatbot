"""Vimeo API: find a downloadable rendition of a lesson video.

Needs a personal access token with the `private` and `video_files` scopes, on an
account plan that allows file downloads via the API.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import get_settings


@dataclass
class VimeoVideo:
    id: str
    name: str
    duration: int
    download_url: str


class VimeoError(RuntimeError):
    pass


def pick_smallest_rendition(downloads: list[dict]) -> dict | None:
    """Audio is all we need, so the smallest video file is the cheapest to fetch."""
    usable = [d for d in downloads or [] if d.get("link")]
    return min(usable, key=lambda d: d.get("size") or float("inf"), default=None)


def get_video(video_id: str) -> VimeoVideo:
    token = get_settings().vimeo_access_token
    if not token:
        raise VimeoError("VIMEO_ACCESS_TOKEN is not configured")
    r = httpx.get(
        f"https://api.vimeo.com/videos/{video_id}",
        params={"fields": "name,duration,download"},
        headers={"Authorization": f"bearer {token}", "Accept": "application/vnd.vimeo.*+json;version=3.4"},
        timeout=30,
    )
    if r.status_code == 404:
        raise VimeoError(f"Vimeo video {video_id} not found or not visible to this token")
    r.raise_for_status()
    data = r.json()
    best = pick_smallest_rendition(data.get("download") or [])
    if best is None:
        raise VimeoError(
            f"Vimeo video {video_id} has no download links. Check the token has the "
            "video_files scope and the account plan allows downloads."
        )
    return VimeoVideo(id=video_id, name=data.get("name", ""), duration=int(data.get("duration") or 0),
                      download_url=best["link"])
