"""Client for the addon running inside an open Blender window.

One short-lived connection per request keeps this stateless: there is no session
to lose when Blender is busy, restarted, or the user toggles the bridge off.
"""

from __future__ import annotations

import json
import socket

from .config import Settings

PROBE_TIMEOUT = 1.0
RECV_CHUNK = 65_536


class BridgeUnavailable(RuntimeError):
    """Raised when no live Blender session is listening."""


class LiveBridge:
    def __init__(self, settings: Settings):
        self._host = settings.host
        self._port = settings.port
        self._timeout = settings.timeout

    @property
    def address(self) -> str:
        return f"{self._host}:{self._port}"

    def is_available(self) -> bool:
        try:
            response = self.request({"type": "ping"}, timeout=PROBE_TIMEOUT)
        except (BridgeUnavailable, OSError, json.JSONDecodeError):
            return False
        return bool(response.get("ok"))

    def request(self, message: dict, timeout: float | None = None) -> dict:
        deadline = timeout or self._timeout
        try:
            connection = socket.create_connection((self._host, self._port), timeout=PROBE_TIMEOUT)
        except OSError as exc:
            raise BridgeUnavailable(
                f"No Blender session is listening on {self.address} ({exc}). "
                "Open Blender, press N in the 3D viewport, go to the MCP tab and "
                "click Start MCP Bridge."
            ) from exc

        with connection:
            connection.settimeout(deadline)
            connection.sendall(json.dumps(message).encode("utf-8") + b"\n")
            return json.loads(_read_line(connection).decode("utf-8"))


def _read_line(connection: socket.socket) -> bytes:
    buffer = bytearray()
    while True:
        try:
            chunk = connection.recv(RECV_CHUNK)
        except TimeoutError as exc:
            raise BridgeUnavailable(
                "Blender accepted the request but never answered. It is probably still "
                "working - check the Blender window."
            ) from exc
        if not chunk:
            raise BridgeUnavailable("Blender closed the connection before answering")
        buffer += chunk
        newline = buffer.find(b"\n")
        if newline != -1:
            return bytes(buffer[:newline])
