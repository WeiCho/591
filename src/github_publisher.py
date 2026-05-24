"""Push the generated HTML report to a GitHub Pages branch via Contents API.

Config (in config.json):
  "github_publish": {
    "repo":  "username/rent-report",   # target repo (must be public for free Pages)
    "token": "ghp_xxxx"                # fine-grained PAT — Contents: Read & Write
  }

The report is always uploaded as `index.html` on the `gh-pages` branch so the
GitHub Pages URL stays constant (https://username.github.io/rent-report/).
"""
from __future__ import annotations
import base64
import json
import logging
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_BRANCH   = "gh-pages"
_FILENAME = "index.html"


def _api(
    token: str,
    method: str,
    url: str,
    body: dict | None = None,
) -> dict:
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept":        "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type":  "application/json",
            "User-Agent":    "rent-monitor-bot",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def _get_sha(token: str, repo: str) -> str | None:
    """Return the blob SHA of index.html on gh-pages, or None if it doesn't exist yet."""
    url = f"https://api.github.com/repos/{repo}/contents/{_FILENAME}?ref={_BRANCH}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept":        "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent":    "rent-monitor-bot",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode()).get("sha")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def publish(html_path: Path, repo: str, token: str) -> str:
    """Upload html_path as index.html to gh-pages. Returns the Pages URL."""
    content_b64 = base64.b64encode(html_path.read_bytes()).decode()
    sha         = _get_sha(token, repo)

    body: dict = {
        "message": f"update report {html_path.stem}",
        "content": content_b64,
        "branch":  _BRANCH,
    }
    if sha:
        body["sha"] = sha

    url = f"https://api.github.com/repos/{repo}/contents/{_FILENAME}"
    _api(token, "PUT", url, body)

    owner = repo.split("/")[0]
    name  = repo.split("/")[1]
    pages_url = f"https://{owner}.github.io/{name}/"
    logger.info("GitHub Pages updated: %s", pages_url)
    return pages_url
