"""A small newline-delimited JSON server that lets an outside process drive Blender.

Sockets are served on background threads, but ``bpy`` is not thread-safe, so every
request is parked on a queue and executed by a timer running on Blender's main
thread. The socket thread blocks until that timer hands back a response.
"""

from __future__ import annotations

import contextlib
import json
import queue
import socket
import threading
import traceback

import bpy

from . import handlers

POLL_INTERVAL = 0.05
RECV_CHUNK = 65_536

_requests: queue.Queue = queue.Queue()
_stop_event: threading.Event | None = None
_accept_thread: threading.Thread | None = None

status = {
    "running": False,
    "host": None,
    "port": None,
    "connections": 0,
    "handled": 0,
    "last_error": None,
}


def is_running() -> bool:
    return status["running"]


def start(host: str, port: int, request_timeout: float) -> None:
    global _stop_event, _accept_thread

    if is_running():
        raise RuntimeError(f"Already listening on {status['host']}:{status['port']}")

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listener.bind((host, port))
        listener.listen(8)
    except OSError as exc:
        listener.close()
        raise RuntimeError(f"Could not listen on {host}:{port} - {exc}") from exc
    listener.settimeout(0.5)

    _stop_event = threading.Event()
    _accept_thread = threading.Thread(
        target=_accept_loop,
        args=(listener, _stop_event, request_timeout),
        name="blender-mcp-accept",
        daemon=True,
    )
    _accept_thread.start()

    status.update(running=True, host=host, port=port, last_error=None)
    if not bpy.app.timers.is_registered(_pump):
        bpy.app.timers.register(_pump, persistent=True)


def stop() -> None:
    global _stop_event, _accept_thread

    if _stop_event is not None:
        _stop_event.set()
    if _accept_thread is not None:
        _accept_thread.join(timeout=2.0)
    _stop_event = None
    _accept_thread = None

    if bpy.app.timers.is_registered(_pump):
        bpy.app.timers.unregister(_pump)
    _drain_pending("Server stopped before this request could run")
    status.update(running=False, host=None, port=None, connections=0)


def _accept_loop(listener: socket.socket, stop_event: threading.Event, timeout: float) -> None:
    try:
        while not stop_event.is_set():
            try:
                connection, _address = listener.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            threading.Thread(
                target=_serve_client,
                args=(connection, stop_event, timeout),
                name="blender-mcp-client",
                daemon=True,
            ).start()
    finally:
        listener.close()


def _serve_client(connection: socket.socket, stop_event: threading.Event, timeout: float) -> None:
    status["connections"] += 1
    connection.settimeout(1.0)
    buffer = b""
    try:
        while not stop_event.is_set():
            try:
                chunk = connection.recv(RECV_CHUNK)
            except TimeoutError:
                continue
            except OSError:
                break
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if not line.strip():
                    continue
                response = _execute_on_main_thread(line, timeout)
                connection.sendall(json.dumps(response).encode("utf-8") + b"\n")
    except Exception:
        status["last_error"] = traceback.format_exc()
    finally:
        status["connections"] = max(0, status["connections"] - 1)
        with contextlib.suppress(OSError):
            connection.close()


def _execute_on_main_thread(raw: bytes, timeout: float) -> dict:
    try:
        message = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"Malformed request: {exc}"}

    ticket = {"message": message, "response": None, "done": threading.Event()}
    _requests.put(ticket)
    if not ticket["done"].wait(timeout):
        return {
            "ok": False,
            "error": (
                f"Blender did not finish this request within {timeout:.0f}s. "
                "It may still be running - check the Blender window."
            ),
        }
    return ticket["response"]


def _pump() -> float:
    """Main-thread timer: run every queued request against bpy."""
    while True:
        try:
            ticket = _requests.get_nowait()
        except queue.Empty:
            break
        try:
            ticket["response"] = handlers.dispatch(ticket["message"])
            status["handled"] += 1
        except Exception:
            ticket["response"] = {"ok": False, "error": traceback.format_exc()}
            status["last_error"] = ticket["response"]["error"]
        finally:
            ticket["done"].set()
    return POLL_INTERVAL


def _drain_pending(reason: str) -> None:
    while True:
        try:
            ticket = _requests.get_nowait()
        except queue.Empty:
            return
        ticket["response"] = {"ok": False, "error": reason}
        ticket["done"].set()
