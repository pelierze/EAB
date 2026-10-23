"""
Check whether a newer GitHub release is available.
"""
import json
import logging
import urllib.request
import re
from dataclasses import dataclass
from typing import Optional

from .app_identity import RELEASE_REPOSITORY, SUPPORTED_RELEASE_REPOSITORIES
from .version import APP_VERSION

logger = logging.getLogger(__name__)

DEFAULT_RELEASE_API_URL = f"https://api.github.com/repos/{RELEASE_REPOSITORY}/releases/latest"
DEFAULT_RELEASES_PAGE_URL = f"https://github.com/{RELEASE_REPOSITORY}/releases/latest"
RELEASE_API_URLS = tuple(f"https://api.github.com/repos/{repo}/releases/latest"
                        for repo in SUPPORTED_RELEASE_REPOSITORIES)


def parse_version(version: str) -> tuple[int, ...]:
    parts = []
    for part in str(version).strip().lstrip("vV").split("."):
        try:
            parts.append(int(part))
        except ValueError:
            digits = "".join(char for char in part if char.isdigit())
            if digits:
                parts.append(int(digits))
            break
    return tuple(parts)


@dataclass
class ReleaseInfo:
    version: str
    url: str
    name: str
    body: str = ""
    assets: tuple = ()


def _fetch_release_at(api_url: str) -> ReleaseInfo:
    request = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": f"EAB/{APP_VERSION}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError(f"unexpected status: {response.status}")
        payload = json.loads(response.read(128 * 1024).decode("utf-8"))

    if not isinstance(payload, dict):
        raise ValueError("release response must be an object")

    version = str(payload.get("tag_name") or payload.get("name") or "").strip()
    fallback_page = api_url.replace("https://api.github.com/repos/", "https://github.com/")
    url = str(payload.get("html_url") or fallback_page).strip()
    name = str(payload.get("name") or version or "새 릴리즈").strip()
    body = str(payload.get("body") or "").strip()

    if not version:
        raise ValueError("release version is missing")

    assets = tuple(payload.get("assets") or ())
    return ReleaseInfo(version=version, url=url, name=name, body=body, assets=assets)


def fetch_latest_release(api_url: str = DEFAULT_RELEASE_API_URL) -> ReleaseInfo:
    # Explicit custom endpoints keep their previous single-address behavior.
    if api_url not in RELEASE_API_URLS:
        return _fetch_release_at(api_url)
    release = _fetch_release_at(api_url)
    if not re.fullmatch(r'v?\d+\.\d+\.\d+', release.version):
        raise ValueError('release is not a stable version')
    return release


def get_available_update(
    current_version: str = APP_VERSION,
    api_url: str = DEFAULT_RELEASE_API_URL,
) -> Optional[ReleaseInfo]:
    try:
        release = fetch_latest_release(api_url)
    except Exception as exc:
        logger.info("릴리즈 업데이트 확인을 건너뜁니다: %s", exc)
        return None

    if parse_version(release.version) > parse_version(current_version):
        return release
    return None
