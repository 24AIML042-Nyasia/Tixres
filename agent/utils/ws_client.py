from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import struct
from dataclasses import dataclass
from typing import Any

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WebSocketClientError(Exception):
    pass


async def _read_until(reader: asyncio.StreamReader, marker: bytes, max_bytes: int) -> bytes:
    # NOTE: StreamReader.readuntil() preserves any extra bytes read beyond the
    # marker inside the StreamReader's internal buffer. That's important because
    # the server may send the first WebSocket frame immediately after the HTTP
    # 101 response, and we must not drop it.
    try:
        data = await reader.readuntil(marker)
    except asyncio.LimitOverrunError as exc:
        raise WebSocketClientError("Response exceeded maximum size") from exc
    except asyncio.IncompleteReadError as exc:
        raise WebSocketClientError("Server closed connection") from exc

    if len(data) > max_bytes:
        raise WebSocketClientError("Response exceeded maximum size")
    return data


def _encode_client_frame(payload: bytes, opcode: int) -> bytes:
    fin_opcode = 0x80 | (opcode & 0x0F)
    length = len(payload)
    mask_bit = 0x80

    if length <= 125:
        header = struct.pack("!BB", fin_opcode, mask_bit | length)
    elif length <= 65535:
        header = struct.pack("!BBH", fin_opcode, mask_bit | 126, length)
    else:
        header = struct.pack("!BBQ", fin_opcode, mask_bit | 127, length)

    mask_key = secrets.token_bytes(4)
    masked = bytearray(payload)
    for i in range(len(masked)):
        masked[i] ^= mask_key[i % 4]

    return header + mask_key + bytes(masked)


async def _read_exact(reader: asyncio.StreamReader, n: int) -> bytes:
    data = await reader.readexactly(n)
    if len(data) != n:
        raise WebSocketClientError("Unexpected EOF")
    return data


@dataclass(frozen=True)
class Frame:
    opcode: int
    payload: bytes
    fin: bool = True


async def _recv_frame(reader: asyncio.StreamReader) -> Frame:
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

    mask_key = b""
    if masked:
        mask_key = await _read_exact(reader, 4)

    payload = await _read_exact(reader, length) if length else b""
    if masked and payload:
        payload_bytes = bytearray(payload)
        for i in range(len(payload_bytes)):
            payload_bytes[i] ^= mask_key[i % 4]
        payload = bytes(payload_bytes)

    return Frame(opcode=opcode, payload=payload, fin=fin)


class WebSocketClient:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self._reader = reader
        self._writer = writer

    @classmethod
    async def connect(cls, host: str = "127.0.0.1", port: int = 8765, path: str = "/"):
        reader, writer = await asyncio.open_connection(host, port)

        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        writer.write(request.encode("utf-8"))
        await writer.drain()

        response = await _read_until(reader, b"\r\n\r\n", max_bytes=64 * 1024)
        header_text = response.decode("utf-8", errors="replace")
        status_line = header_text.split("\r\n", 1)[0]
        if " 101 " not in status_line:
            raise WebSocketClientError(f"Unexpected handshake status: {status_line}")

        # Basic accept verification
        accept_expected = base64.b64encode(
            hashlib.sha1((key + WS_GUID).encode("utf-8")).digest()
        ).decode("ascii")
        if f"sec-websocket-accept: {accept_expected}".lower() not in header_text.lower():
            raise WebSocketClientError("Invalid Sec-WebSocket-Accept")

        return cls(reader, writer)

    async def send_json(self, obj: Any) -> None:
        payload = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self._writer.write(_encode_client_frame(payload, opcode=0x1))
        await self._writer.drain()

    async def recv_json(self) -> dict[str, Any] | None:
        while True:
            frame = await _recv_frame(self._reader)
            if not frame.fin:
                raise WebSocketClientError("Fragmented frames not supported")
            if frame.opcode == 0x8:  # close
                return None
            if frame.opcode == 0x9:  # ping
                self._writer.write(_encode_client_frame(frame.payload, opcode=0xA))
                await self._writer.drain()
                continue
            if frame.opcode == 0xA:  # pong
                continue
            if frame.opcode != 0x1:
                continue

            text = frame.payload.decode("utf-8", errors="replace")
            obj = json.loads(text)
            if not isinstance(obj, dict):
                raise WebSocketClientError("Message must be a JSON object")
            return obj

    async def close(self) -> None:
        self._writer.write(_encode_client_frame(b"", opcode=0x8))
        await self._writer.drain()
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except Exception:
            pass
