"""Shared HTTP fetch helper.

Wraps ``curl`` via subprocess. Single point of control for timeout,
retries, and default headers. Used by ``fetch_feeds.py`` and
``fetch_hotlist.py``.
"""

from __future__ import annotations

import subprocess
from typing import Mapping


DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; FeedBot/1.0)"


def fetch_url(
    url: str,
    headers: Mapping[str, str] | None = None,
    timeout: int = 15,
) -> str | None:
    """Fetch ``url`` with ``curl`` and return the response body.

    Args:
        url: URL to fetch.
        headers: Optional HTTP headers. If ``User-Agent`` is not present a
            default ``FeedBot/1.0`` agent is added.
        timeout: ``curl --max-time`` seconds. The surrounding subprocess
            uses ``timeout + 5`` so curl always exits first.

    Returns:
        Response body as text on success, ``None`` on any failure.
    """
    args: list[str] = ["curl", "-sL", "--max-time", str(timeout)]

    merged: dict[str, str] = dict(headers or {})
    has_ua = any(k.lower() == "user-agent" for k in merged)
    if not has_ua:
        merged["User-Agent"] = DEFAULT_USER_AGENT

    for key, value in merged.items():
        args.extend(["-H", f"{key}: {value}"])

    args.append(url)

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )
    except Exception:
        return None
    return result.stdout if result.returncode == 0 else None
