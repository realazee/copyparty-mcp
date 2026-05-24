# copyparty-mcp

An [MCP](https://modelcontextprotocol.io/) server that connects AI agents to a [Copyparty](https://github.com/9001/copyparty) file server — enabling directory browsing, file reading for RAG/knowledge, full-text search, and file uploads.

## Features

- **📂 Browse** — List files and directories on your Copyparty server
- **📄 Read** — Download and read file contents (text and binary) for RAG ingestion
- **🔎 Search** — Full-text search across all indexed files by name, tags, or metadata
- **📤 Upload** — Upload files to user-defined writable directories
- **✏️ Write** — Create or overwrite text files
- **🗑️ Delete** — Remove files from writable directories
- **🔒 Safe** — Write operations are restricted to explicitly configured directories

## Quick Start

### Install

```bash
# Clone the repo
git clone https://github.com/user/copyparty-mcp.git
cd copyparty-mcp

# Install with pip
pip install -e .

# Or with uv
uv pip install -e .
```

### Configure

Set the following environment variables (or create a `.env` file — see `.env.example`):

| Variable | Required | Default | Description |
|----------|---------|---------|-------------|
| `COPYPARTY_BASE_URL` | ✅ | — | Base URL of your Copyparty server |
| `COPYPARTY_USERNAME` | ❌ | `""` | Username (only if Copyparty uses `--usernames` mode) |
| `COPYPARTY_PASSWORD` | ❌ | `""` | Password for authentication |
| `COPYPARTY_WRITABLE_DIRS` | ❌ | `""` | Comma-separated directories the agent can write to |
| `COPYPARTY_MAX_FILE_SIZE` | ❌ | `10485760` | Max readable file size in bytes (default 10 MB) |

**Option A: `.env` file (recommended)**

```bash
cp .env.example .env
# Edit .env with your values
```

**Option B: Shell environment**

```bash
export COPYPARTY_BASE_URL="https://files.example.com"
export COPYPARTY_PASSWORD="your-password-here"
export COPYPARTY_WRITABLE_DIRS="/uploads,/notes/ai,/scratch"
```

### Run

```bash
# Direct
python -m copyparty_mcp.server

# Or via the installed entry point
copyparty-mcp
```

## Client Configuration

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "copyparty": {
      "command": "python",
      "args": ["-m", "copyparty_mcp.server"],
      "env": {
        "COPYPARTY_BASE_URL": "https://files.example.com",
        "COPYPARTY_PASSWORD": "your-password-here",
        "COPYPARTY_WRITABLE_DIRS": "/uploads,/notes/ai"
      }
    }
  }
}
```

### Claude Desktop (with uv)

```json
{
  "mcpServers": {
    "copyparty": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/copyparty-mcp", "python", "-m", "copyparty_mcp.server"],
      "env": {
        "COPYPARTY_BASE_URL": "https://files.example.com",
        "COPYPARTY_PASSWORD": "your-password-here",
        "COPYPARTY_WRITABLE_DIRS": "/uploads,/notes/ai"
      }
    }
  }
}
```

### Cursor / VS Code

Add to your `.cursor/mcp.json` or equivalent:

```json
{
  "mcpServers": {
    "copyparty": {
      "command": "python",
      "args": ["-m", "copyparty_mcp.server"],
      "env": {
        "COPYPARTY_BASE_URL": "https://files.example.com",
        "COPYPARTY_PASSWORD": "your-password-here",
        "COPYPARTY_WRITABLE_DIRS": "/uploads"
      }
    }
  }
}
```

## Available Tools

### Read Operations

| Tool | Description |
|------|-------------|
| `list_directory` | List files and folders at a path |
| `read_file` | Read file contents (text returned directly, binary as base64) |
| `search_files` | Search files by name, path, tags, or metadata |
| `get_file_info` | Get file metadata (size, type, modified date) |

### Write Operations

All write operations require the target path to be inside a directory listed in `COPYPARTY_WRITABLE_DIRS`.

| Tool | Description |
|------|-------------|
| `upload_file` | Upload a file (text or base64-encoded binary) |
| `write_file` | Write or overwrite a text file |
| `create_directory` | Create a new subdirectory |
| `delete_file` | Delete a file or folder (recursive) |
| `move_file` | Move or rename a file or folder |

## Security

Write operations are **denied by default**. You must explicitly list writable directories via `COPYPARTY_WRITABLE_DIRS`. The check is prefix-based — if `/uploads` is listed, then `/uploads/subfolder/file.txt` is also writable, but `/other/uploads` is not.

If `COPYPARTY_WRITABLE_DIRS` is empty or unset, all write tools will return an error.

## Development

```bash
# Install in development mode
pip install -e .

# Test with the MCP Inspector
npx @modelcontextprotocol/inspector python -m copyparty_mcp.server
```

## License

MIT
