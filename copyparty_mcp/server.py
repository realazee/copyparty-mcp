"""Copyparty MCP Server.

Exposes a Copyparty file server to AI agents via the Model Context Protocol,
enabling directory browsing, file reading (for RAG / knowledge), searching,
and writing to user-defined directories.

All configuration is driven by environment variables — see :mod:`copyparty_mcp.config`.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import CopypartyClient
from .config import Config, load_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "copyparty",
    instructions=(
        "MCP server for Copyparty — browse directories, read files, "
        "search, and upload to a self-hosted Copyparty file server."
    ),
)

# Lazy-initialised singletons — created on first tool call so the server
# can still import cleanly in tests even without env vars.
_config: Config | None = None
_client: CopypartyClient | None = None


def _get_config() -> Config:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def _get_client() -> CopypartyClient:
    global _client
    if _client is None:
        _client = CopypartyClient(_get_config())
    return _client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_writable(path: str) -> None:
    """Raise if *path* is not inside a user-configured writable directory."""
    cfg = _get_config()
    if not cfg.is_writable(path):
        allowed = ", ".join(sorted(cfg.writable_dirs)) if cfg.writable_dirs else "(none)"
        raise ValueError(
            f"Write access denied: '{path}' is not inside a writable directory. "
            f"Writable directories: {allowed}. "
            f"Configure COPYPARTY_WRITABLE_DIRS to allow writes."
        )


def _is_text_content(content_type: str) -> bool:
    """Guess whether *content_type* represents text."""
    ct = content_type.lower().split(";")[0].strip()
    if ct.startswith("text/"):
        return True
    text_types = {
        "application/json",
        "application/xml",
        "application/javascript",
        "application/x-yaml",
        "application/yaml",
        "application/toml",
        "application/x-sh",
        "application/xhtml+xml",
        "application/svg+xml",
    }
    return ct in text_types


def _format_file_entry(entry: dict[str, Any]) -> str:
    """Format a single file/dir entry from a Copyparty listing into a readable line."""
    name = entry.get("href", entry.get("name", "?"))
    size = entry.get("sz", "")
    ts = entry.get("ts", "")
    dt = entry.get("dt", "")
    if size != "":
        size_str = _human_size(int(size))
    else:
        size_str = ""

    parts = [name]
    if size_str:
        parts.append(f"({size_str})")
    if dt:
        parts.append(f"[{dt}]")
    elif ts:
        parts.append(f"[ts:{ts}]")
    return "  ".join(parts)


def _human_size(n: int) -> str:
    """Format byte count into a human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n //= 1024  # type: ignore[assignment]
    return f"{n:.1f} PB"


# ---------------------------------------------------------------------------
# Tools — Read
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_directory(path: str = "/", include_dotfiles: bool = False) -> str:
    """List files and folders at a path on the Copyparty server.

    Returns file names, sizes, and dates for everything in the directory.
    Use this to explore the file structure before reading specific files.

    Args:
        path: Directory path to list (e.g. "/" or "/documents/notes").
        include_dotfiles: Whether to include hidden dotfiles in the listing.
    """
    client = _get_client()
    try:
        data = await client.list_directory(path, include_dotfiles=include_dotfiles)
    except Exception as e:
        return f"Error listing '{path}': {e}"

    lines: list[str] = [f"📂 Contents of {path}\n"]

    # Copyparty ?ls returns {"dirs": [...], "files": [...]} (among other keys)
    dirs = data.get("dirs", [])
    files = data.get("files", [])

    if dirs:
        lines.append("Directories:")
        for d in dirs:
            if isinstance(d, dict):
                lines.append(f"  📁 {_format_file_entry(d)}")
            else:
                lines.append(f"  📁 {d}")

    if files:
        lines.append("Files:")
        for f in files:
            if isinstance(f, dict):
                lines.append(f"  📄 {_format_file_entry(f)}")
            else:
                lines.append(f"  📄 {f}")

    if not dirs and not files:
        lines.append("(empty directory)")

    return "\n".join(lines)


@mcp.tool()
async def read_file(path: str) -> str:
    """Read the contents of a file from the Copyparty server.

    For text files (source code, markdown, config files, etc.) the raw text
    content is returned directly.  For binary files the content is returned
    as a base64-encoded string.

    This is the main tool for ingesting knowledge and documents for RAG.

    Args:
        path: Path to the file to read (e.g. "/documents/notes.md").
    """
    client = _get_client()
    cfg = _get_config()

    try:
        content, content_type = await client.read_file(path)
    except Exception as e:
        return f"Error reading '{path}': {e}"

    if len(content) > cfg.max_file_size:
        return (
            f"File at '{path}' is {_human_size(len(content))} which exceeds the "
            f"configured limit of {_human_size(cfg.max_file_size)}. "
            f"Adjust COPYPARTY_MAX_FILE_SIZE to read larger files."
        )

    if _is_text_content(content_type):
        # Try UTF-8, fall back to latin-1 which never fails
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
        return text
    else:
        b64 = base64.b64encode(content).decode("ascii")
        return (
            f"[Binary file: {content_type}, {_human_size(len(content))}]\n"
            f"Base64-encoded content:\n{b64}"
        )


@mcp.tool()
async def search_files(query: str) -> str:
    """Search for files across all indexed volumes on the Copyparty server.

    Searches by filename, path, tags, and metadata.  Copyparty supports a
    rich query syntax — for example ``*.md`` to find Markdown files, or tag
    queries like ``artist=someone``.

    Args:
        query: Search query string.
    """
    client = _get_client()
    try:
        data = await client.search(query)
    except Exception as e:
        return f"Error searching for '{query}': {e}"

    # Copyparty returns search results under various keys depending on version
    results = data if isinstance(data, list) else data.get("hits", data.get("res", []))

    if not results:
        return f"No results found for query: {query}"

    lines: list[str] = [f"🔎 Search results for '{query}':\n"]
    if isinstance(results, list):
        for i, item in enumerate(results, 1):
            if isinstance(item, dict):
                rp = item.get("rp", item.get("vp", ""))
                sz = item.get("sz", "")
                info = f"  {i}. {rp}"
                if sz:
                    info += f"  ({_human_size(int(sz))})"
                lines.append(info)
            else:
                lines.append(f"  {i}. {item}")
    else:
        # Unexpected shape — dump as JSON for transparency
        lines.append(json.dumps(data, indent=2))

    return "\n".join(lines)


@mcp.tool()
async def get_file_info(path: str) -> str:
    """Get metadata for a file without downloading it.

    Returns information like file size, content type, and last modified date.

    Args:
        path: Path to the file (e.g. "/photos/sunset.jpg").
    """
    client = _get_client()
    try:
        headers = await client.get_file_info(path)
    except Exception as e:
        return f"Error getting info for '{path}': {e}"

    interesting = {
        "content-type": "Type",
        "content-length": "Size",
        "last-modified": "Modified",
        "etag": "ETag",
    }

    lines: list[str] = [f"ℹ️  File info for {path}\n"]
    for header, label in interesting.items():
        val = headers.get(header)
        if val:
            if header == "content-length":
                val = f"{val} bytes ({_human_size(int(val))})"
            lines.append(f"  {label}: {val}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tools — Write
# ---------------------------------------------------------------------------

@mcp.tool()
async def upload_file(
    directory: str,
    filename: str,
    content: str,
    encoding: str = "text",
) -> str:
    """Upload a file to a writable directory on the Copyparty server.

    Only directories listed in the COPYPARTY_WRITABLE_DIRS configuration
    are accepted.  The content can be provided as plain text or as a
    base64-encoded string for binary files.

    Args:
        directory: Target directory path (e.g. "/uploads" or "/notes/ai").
        filename: Name for the uploaded file.
        content: File content as a string.
        encoding: "text" for plain text content, "base64" for base64-encoded binary.
    """
    try:
        _assert_writable(directory)
    except ValueError as e:
        return str(e)

    if encoding == "base64":
        try:
            raw = base64.b64decode(content)
        except Exception:
            return "Error: invalid base64 content."
    else:
        raw = content.encode("utf-8")

    client = _get_client()
    try:
        result = await client.upload_file(directory, filename, raw)
        return f"Uploaded '{filename}' to {directory}\nServer response: {json.dumps(result)}"
    except Exception as e:
        return f"Error uploading '{filename}' to '{directory}': {e}"


@mcp.tool()
async def write_file(path: str, content: str) -> str:
    """Write or overwrite a text file on the Copyparty server.

    The file's parent directory must be inside a writable directory configured
    via COPYPARTY_WRITABLE_DIRS.

    Args:
        path: Full path for the file (e.g. "/notes/ai/summary.md").
        content: Text content to write.
    """
    # Check the parent directory
    parent = "/".join(path.rstrip("/").split("/")[:-1]) or "/"
    try:
        _assert_writable(parent)
    except ValueError as e:
        return str(e)

    client = _get_client()
    try:
        result = await client.write_file(path, content.encode("utf-8"))
        return f"Wrote file at {path}\nServer response: {json.dumps(result)}"
    except Exception as e:
        return f"Error writing '{path}': {e}"


@mcp.tool()
async def create_directory(path: str, name: str) -> str:
    """Create a new subdirectory inside a writable directory on the Copyparty server.

    Args:
        path: Parent directory path (e.g. "/uploads").
        name: Name of the new subdirectory to create.
    """
    try:
        _assert_writable(path)
    except ValueError as e:
        return str(e)

    client = _get_client()
    try:
        await client.mkdir(path, name)
        return f"Created directory '{name}' inside {path}"
    except Exception as e:
        return f"Error creating directory '{name}' in '{path}': {e}"


@mcp.tool()
async def delete_file(path: str) -> str:
    """Delete a file or folder on the Copyparty server.

    The path must be inside a writable directory configured via
    COPYPARTY_WRITABLE_DIRS.  Deletion is recursive for directories.

    Args:
        path: Path to delete (e.g. "/uploads/old-file.txt").
    """
    try:
        _assert_writable(path)
    except ValueError as e:
        return str(e)

    client = _get_client()
    try:
        await client.delete(path)
        return f"Deleted {path}"
    except Exception as e:
        return f"Error deleting '{path}': {e}"


@mcp.tool()
async def move_file(src: str, dst: str) -> str:
    """Move or rename a file or folder on the Copyparty server.

    Both the source and destination paths must be inside a writable directory
    configured via COPYPARTY_WRITABLE_DIRS.

    Args:
        src: Source path of the file or folder to move (e.g. "/uploads/old.txt").
        dst: Target path (e.g. "/uploads/new.txt").
    """
    try:
        _assert_writable(src)
        _assert_writable(dst)
    except ValueError as e:
        return str(e)

    client = _get_client()
    try:
        await client.move(src, dst)
        return f"Moved '{src}' to '{dst}'"
    except Exception as e:
        return f"Error moving '{src}' to '{dst}': {e}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
