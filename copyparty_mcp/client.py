"""Async HTTP client for the Copyparty REST API.

This module wraps Copyparty's documented HTTP API (see
https://github.com/9001/copyparty/blob/hovudstraum/docs/devnotes.md#http-api)
into a small, typed, async client powered by ``httpx``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from .config import Config

logger = logging.getLogger(__name__)


class CopypartyClient:
    """Lightweight async wrapper around Copyparty's HTTP API.

    Parameters:
        config: A :class:`Config` instance with base URL and credentials.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        # Authenticate via the ``PW:`` header rather than ``?pw=`` URL params
        # to avoid leaking credentials in error messages, logs, and proxy logs.
        # Format: ``PW: password`` or ``PW: username:password`` depending on
        # whether the server uses ``--usernames``.
        headers: dict[str, str] = {}
        if config.auth_credential:
            headers["PW"] = config.auth_credential
        self._http = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
            headers=headers,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _auth_params(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Return query-string parameters for the request."""
        params: dict[str, str] = {}
        if extra:
            params.update(extra)
        return params

    @staticmethod
    def _ensure_path(path: str) -> str:
        """Normalise *path* so it starts with ``/``."""
        path = path.strip()
        if not path.startswith("/"):
            path = "/" + path
        return path

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def list_directory(
        self, path: str = "/", *, include_dotfiles: bool = False
    ) -> dict[str, Any]:
        """Return a JSON directory listing for *path*.

        Uses ``GET /<path>?ls`` which returns the folder contents as JSON.
        """
        path = self._ensure_path(path)
        params = self._auth_params({"ls": ""})
        if include_dotfiles:
            params["dots"] = ""
        resp = await self._http.get(path, params=params)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    async def read_file(self, path: str) -> tuple[bytes, str]:
        """Download the file at *path*.

        Returns:
            A ``(content_bytes, content_type)`` tuple.
        """
        path = self._ensure_path(path)
        resp = await self._http.get(path, params=self._auth_params())
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "application/octet-stream")
        return resp.content, content_type

    async def get_file_info(self, path: str) -> dict[str, str]:
        """``HEAD`` request to get file metadata without downloading."""
        path = self._ensure_path(path)
        resp = await self._http.head(path, params=self._auth_params())
        resp.raise_for_status()
        return dict(resp.headers)

    async def search(self, query: str) -> dict[str, Any]:
        """Server-wide file search.

        Uses ``jPOST / {"q":"<query>"}`` which searches by name, tags, and
        metadata across all indexed volumes.
        """
        resp = await self._http.post(
            "/",
            params=self._auth_params(),
            json={"q": query},
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def upload_file(
        self,
        directory: str,
        filename: str,
        content: bytes,
    ) -> dict[str, Any]:
        """Upload *content* as *filename* into *directory* via ``PUT``.

        Returns the JSON response from Copyparty.
        """
        directory = self._ensure_path(directory).rstrip("/")
        upload_path = f"{directory}/{filename}"
        resp = await self._http.put(
            upload_path,
            params=self._auth_params({"j": ""}),
            content=content,
            headers={"Content-Type": "application/octet-stream"},
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    async def write_file(
        self,
        path: str,
        content: bytes,
        *,
        replace: bool = True,
    ) -> dict[str, Any]:
        """Write (or overwrite) a file at *path* via ``PUT``.

        When *replace* is ``True`` the ``Replace: 1`` header is sent so
        existing files are overwritten.
        """
        path = self._ensure_path(path)
        headers: dict[str, str] = {"Content-Type": "application/octet-stream"}
        if replace:
            headers["Replace"] = "1"
        resp = await self._http.put(
            path,
            params=self._auth_params({"j": ""}),
            content=content,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    async def mkdir(self, path: str, name: str) -> bool:
        """Create directory *name* inside *path* via multipart POST."""
        path = self._ensure_path(path)
        resp = await self._http.post(
            path,
            params=self._auth_params(),
            data={"act": "mkdir", "name": name},
        )
        resp.raise_for_status()
        return True

    async def delete(self, path: str) -> bool:
        """Delete the file or folder at *path* (recursively).

        Uses ``POST /<path>?delete``.
        """
        path = self._ensure_path(path)
        resp = await self._http.post(
            path,
            params=self._auth_params({"delete": ""}),
        )
        resp.raise_for_status()
        return True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()
