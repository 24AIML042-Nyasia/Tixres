from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Final
from urllib.parse import unquote, urlsplit


_MIME_TYPES: Final[dict[str, str]] = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
}


def _http_response(status: str, headers: dict[str, str], body: bytes = b"") -> bytes:
    header_lines = [f"HTTP/1.1 {status}\r\n"]
    for k, v in headers.items():
        header_lines.append(f"{k}: {v}\r\n")
    header_lines.append("\r\n")
    return "".join(header_lines).encode("utf-8") + body


def _safe_join(root: Path, url_path: str) -> Path | None:
    # Strip query/fragment then URL-decode.
    path = urlsplit(url_path).path
    path = unquote(path)

    if not path.startswith("/"):
        path = "/" + path

    # Default doc
    if path == "/":
        path = "/index.html"

    # Prevent traversal
    rel = Path(path.lstrip("/"))
    if any(part in ("..", "") for part in rel.parts):
        return None

    full = (root / rel).resolve()
    try:
        root_resolved = root.resolve()
    except Exception:
        root_resolved = root
    if root_resolved not in full.parents and full != root_resolved:
        return None
    return full


async def handle_static_http(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    root: Path,
) -> None:
    try:
        data = await reader.readuntil(b"\r\n\r\n")
    except Exception:
        writer.close()
        return

    try:
        head = data.decode("utf-8", errors="replace")
        first = head.split("\r\n", 1)[0]
        method, path, _ = first.split(" ", 2)
        method = method.upper()
    except Exception:
        writer.write(_http_response("400 Bad Request", {"Content-Length": "0"}))
        await writer.drain()
        writer.close()
        return

    if method not in ("GET", "HEAD"):
        writer.write(
            _http_response(
                "405 Method Not Allowed",
                {"Content-Length": "0", "Allow": "GET, HEAD"},
            )
        )
        await writer.drain()
        writer.close()
        return

    file_path = _safe_join(root, path)
    if file_path is None or not file_path.exists() or not file_path.is_file():
        try:
            print(f"[UI] 404 {method} {path}")
        except Exception:
            pass
        body = b"Not Found"
        writer.write(
            _http_response(
                "404 Not Found",
                {
                    "Content-Type": "text/plain; charset=utf-8",
                    "Content-Length": str(len(body)),
                },
                body if method == "GET" else b"",
            )
        )
        await writer.drain()
        writer.close()
        return

    content = file_path.read_bytes()
    ctype = _MIME_TYPES.get(file_path.suffix.lower(), "application/octet-stream")

    writer.write(
        _http_response(
            "200 OK",
            {
                "Content-Type": ctype,
                "Content-Length": str(len(content)),
                "Cache-Control": "no-cache",
            },
            content if method == "GET" else b"",
        )
    )
    await writer.drain()
    writer.close()
