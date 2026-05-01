from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import struct
from dataclasses import dataclass
from typing import Any

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WebSocketError(Exception):
    pass


class WebSocketHandshakeError(WebSocketError):
    pass


async def _read_until(reader: asyncio.StreamReader, marker: bytes, max_bytes: int) -> bytes:
    # StreamReader.readuntil() preserves any extra bytes beyond marker in its
    # internal buffer. This avoids dropping data if a client pipelines frames.
    try:
        data = await reader.readuntil(marker)
    except asyncio.LimitOverrunError as exc:
        raise WebSocketHandshakeError("Handshake exceeded maximum size") from exc
    except asyncio.IncompleteReadError as exc:
        raise WebSocketHandshakeError("Client closed connection during handshake") from exc

    if len(data) > max_bytes:
        raise WebSocketHandshakeError("Handshake exceeded maximum size")
    return data


def _parse_http_headers(request: bytes) -> dict[str, str]:
    text = request.decode("utf-8", errors="replace")
    lines = text.split("\r\n")
    if not lines:
        raise WebSocketHandshakeError("Empty handshake")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            break
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        headers[k.strip().lower()] = v.strip()
    return headers


async def handshake(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    request = await _read_until(reader, b"\r\n\r\n", max_bytes=64 * 1024)
    headers = _parse_http_headers(request)

    key = headers.get("sec-websocket-key")
    if not key:
        raise WebSocketHandshakeError("Missing Sec-WebSocket-Key")

    accept = base64.b64encode(
        hashlib.sha1((key + WS_GUID).encode("utf-8")).digest()
    ).decode("ascii")

    response = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n"
        "\r\n"
    )
    writer.write(response.encode("utf-8"))
    await writer.drain()


async def _read_exact(reader: asyncio.StreamReader, n: int) -> bytes:
    data = await reader.readexactly(n)
    if len(data) != n:
        raise WebSocketError("Unexpected EOF")
    return data


@dataclass(frozen=True)
class Frame:
    opcode: int
    payload: bytes
    fin: bool = True


def _encode_frame(payload: bytes, opcode: int) -> bytes:
    fin_opcode = 0x80 | (opcode & 0x0F)
    length = len(payload)

    if length <= 125:
        header = struct.pack("!BB", fin_opcode, length)
    elif length <= 65535:
        header = struct.pack("!BBH", fin_opcode, 126, length)
    else:
        header = struct.pack("!BBQ", fin_opcode, 127, length)

    return header + payload


async def recv_frame(reader: asyncio.StreamReader) -> Frame:
    b1 = (await _read_exact(reader, 1))[0]
    b2 = (await _read_exact(reader, 1))[0]

    fin = bool(b1 & 0x80)
    opcode = b1 & 0x0F
    masked = bool(b2 & 0x80)
    length = b2 & 0x7F

    if length == 126:
        length = struct.unpack("!H", await _read_exact(reader, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", await _read_exact(reader, 8))[0]

    if not masked:
        raise WebSocketError("Client frames must be masked")

    mask_key = await _read_exact(reader, 4)

    payload = await _read_exact(reader, length) if length else b""
    if payload:
        payload_bytes = bytearray(payload)
        for i in range(len(payload_bytes)):
            payload_bytes[i] ^= mask_key[i % 4]
        payload = bytes(payload_bytes)

    return Frame(opcode=opcode, payload=payload, fin=fin)


class WebSocket:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self._reader = reader
        self._writer = writer

    async def send_text(self, text: str) -> None:
        self._writer.write(_encode_frame(text.encode("utf-8"), opcode=0x1))
        await self._writer.drain()

    async def send_json(self, obj: Any) -> None:
        await self.send_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))

    async def close(self, code: int = 1000, reason: str = "") -> None:
        payload = struct.pack("!H", code) + reason.encode("utf-8")
        self._writer.write(_encode_frame(payload, opcode=0x8))
        await self._writer.drain()

    async def recv_text(self) -> str | None:
        while True:
            frame = await recv_frame(self._reader)
            if not frame.fin:
                raise WebSocketError("Fragmented frames not supported")

            if frame.opcode == 0x8:  # close
                return None
            if frame.opcode == 0x9:  # ping
                self._writer.write(_encode_frame(frame.payload, opcode=0xA))
                await self._writer.drain()
                continue
            if frame.opcode == 0xA:  # pong
                continue
            if frame.opcode != 0x1:
                continue

            return frame.payload.decode("utf-8", errors="replace")

    async def recv_json(self) -> dict[str, Any] | None:
        text = await self.recv_text()
        if text is None:
            return None
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            raise WebSocketError(f"Invalid JSON: {exc}") from exc
        if not isinstance(obj, dict):
            raise WebSocketError("Message must be a JSON object")
        return obj
