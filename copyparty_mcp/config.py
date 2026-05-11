"""Configuration for the Copyparty MCP server.

All settings are read from environment variables so nothing is hardcoded.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    """Immutable server configuration parsed from environment variables.

    Attributes:
        base_url: Base URL of the Copyparty server (e.g. ``http://localhost:3923``).
        username: Optional username for Copyparty authentication (requires
            the server to be running with ``--usernames``).
        password: Optional password for Copyparty authentication.
        writable_dirs: Set of directory paths the agent is allowed to write to.
        max_file_size: Maximum file size in bytes the agent will read (default 10 MB).
    """

    base_url: str
    username: str = ""
    password: str = ""
    writable_dirs: set[str] = field(default_factory=set)
    max_file_size: int = 10 * 1024 * 1024  # 10 MB

    @property
    def auth_credential(self) -> str:
        """Build the credential string for the ``PW:`` header.

        Returns ``username:password`` when a username is configured,
        otherwise just ``password``.  Returns an empty string when no
        password is set.
        """
        if not self.password:
            return ""
        if self.username:
            return f"{self.username}:{self.password}"
        return self.password

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def is_writable(self, path: str) -> bool:
        """Check whether *path* falls inside one of the writable directories.

        The check is prefix-based: if ``/uploads`` is writable then
        ``/uploads/foo/bar.txt`` is also writable.
        """
        if not self.writable_dirs:
            return False
        normalized = _normalize_path(path)
        return any(
            normalized == w or normalized.startswith(w.rstrip("/") + "/")
            for w in self.writable_dirs
        )


def _normalize_path(path: str) -> str:
    """Ensure *path* starts with ``/`` and has no trailing slash (except root)."""
    path = path.strip()
    if not path.startswith("/"):
        path = "/" + path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return path


def load_config() -> Config:
    """Build a :class:`Config` from the current environment.

    A ``.env`` file in the current working directory (or next to this package)
    will be loaded automatically if present.

    Raises:
        SystemExit: If ``COPYPARTY_BASE_URL`` is not set.
    """
    # Load .env from CWD or from the project root (next to pyproject.toml)
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path, override=False)

    base_url = os.environ.get("COPYPARTY_BASE_URL", "").rstrip("/")
    if not base_url:
        raise SystemExit(
            "COPYPARTY_BASE_URL environment variable is required.\n"
            "Example: COPYPARTY_BASE_URL=http://localhost:3923"
        )

    username = os.environ.get("COPYPARTY_USERNAME", "")
    password = os.environ.get("COPYPARTY_PASSWORD", "")

    raw_dirs = os.environ.get("COPYPARTY_WRITABLE_DIRS", "")
    writable_dirs: set[str] = set()
    if raw_dirs:
        writable_dirs = {_normalize_path(d) for d in raw_dirs.split(",") if d.strip()}

    max_file_size = int(
        os.environ.get("COPYPARTY_MAX_FILE_SIZE", str(10 * 1024 * 1024))
    )

    return Config(
        base_url=base_url,
        username=username,
        password=password,
        writable_dirs=writable_dirs,
        max_file_size=max_file_size,
    )
