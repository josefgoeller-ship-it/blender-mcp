"""Prove the live bridge works end to end.

Talks to a Blender window you already have open. If none is listening, it opens one
itself, runs the checks, and closes it again.

    uv run python scripts/verify_live_bridge.py
"""

from __future__ import annotations

import subprocess
import sys
import time

from blender_mcp.bridge import LiveBridge
from blender_mcp.config import get_settings

STARTUP = (
    "import bpy\n"
    "from bl_ext.user_default.blender_mcp_bridge import tcp_server\n"
    "tcp_server.start('{host}', {port}, 600.0)\n"
    "print('[verify] bridge listening')\n"
)
LAUNCH_TIMEOUT = 120.0


def wait_until_available(bridge: LiveBridge, deadline: float) -> bool:
    while time.monotonic() < deadline:
        if bridge.is_available():
            return True
        time.sleep(1.0)
    return False


def check(bridge: LiveBridge) -> int:
    failures = 0

    ping = bridge.request({"type": "ping"})
    print(f"ping            -> {ping}")
    failures += not ping.get("ok")

    added = bridge.request(
        {
            "type": "execute",
            "code": (
                "bpy.ops.mesh.primitive_torus_add(location=(0, 0, 2))\n"
                "bpy.context.active_object.name = 'BridgeCheck'\n"
                "result = bpy.context.active_object.name"
            ),
        }
    )
    print(f"add object      -> {added}")
    failures += not added.get("ok") or added.get("result") != "BridgeCheck"

    info = bridge.request({"type": "scene_info", "include_objects": True})
    names = [obj["name"] for obj in info["result"]["objects"]] if info.get("ok") else []
    print(f"scene objects   -> {names}")
    failures += "BridgeCheck" not in names

    cleaned = bridge.request(
        {
            "type": "execute",
            "code": (
                "obj = bpy.data.objects.get('BridgeCheck')\n"
                "bpy.data.objects.remove(obj, do_unlink=True) if obj else None\n"
                "result = 'removed'"
            ),
        }
    )
    print(f"cleanup         -> {cleaned}")
    failures += not cleaned.get("ok")

    return failures


def main() -> int:
    settings = get_settings()
    bridge = LiveBridge(settings)

    launched: subprocess.Popen | None = None
    if bridge.is_available():
        print(f"Using the Blender session already listening on {bridge.address}\n")
    else:
        print(f"Nothing on {bridge.address}; opening a Blender window for the check...")
        launched = subprocess.Popen(
            [
                str(settings.executable),
                "--python-expr",
                STARTUP.format(host=settings.host, port=settings.port),
            ]
        )
        if not wait_until_available(bridge, time.monotonic() + LAUNCH_TIMEOUT):
            launched.terminate()
            print("Blender never started listening. Check the Blender console for errors.")
            return 1
        print("Bridge is up.\n")

    try:
        failures = check(bridge)
    finally:
        if launched is not None:
            print("\nClosing the Blender window we opened.")
            launched.terminate()
            try:
                launched.wait(timeout=15)
            except subprocess.TimeoutExpired:
                launched.kill()

    print("\nAll live bridge checks passed." if not failures else f"\n{failures} check(s) failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
