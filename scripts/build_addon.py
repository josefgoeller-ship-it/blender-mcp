"""Build the Blender extension zip, and optionally install it.

    uv run python scripts/build_addon.py --install

Uses whichever Blender the MCP server itself would use, so the addon always lands
in the same Blender the server talks to.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from blender_mcp.config import get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_ROOT / "addon" / "blender_mcp_addon"
DIST_DIR = PROJECT_ROOT / "dist"


def run(command: list[str]) -> None:
    print(f"$ {' '.join(command)}")
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"Command failed with exit code {completed.returncode}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install the built zip into Blender and enable it",
    )
    arguments = parser.parse_args()

    blender = str(get_settings().executable)
    DIST_DIR.mkdir(exist_ok=True)

    run([blender, "--command", "extension", "validate", str(SOURCE_DIR)])
    run(
        [
            blender,
            "--command",
            "extension",
            "build",
            "--source-dir",
            str(SOURCE_DIR),
            "--output-dir",
            str(DIST_DIR),
        ]
    )

    archives = sorted(DIST_DIR.glob("blender_mcp_bridge-*.zip"))
    if not archives:
        raise SystemExit("The build produced no zip")
    archive = archives[-1]
    print(f"\nBuilt {archive}")

    if arguments.install:
        run(
            [
                blender,
                "--command",
                "extension",
                "install-file",
                "-r",
                "user_default",
                "-e",
                str(archive),
            ]
        )
        print("\nInstalled and enabled. Restart Blender if it is currently open.")
    else:
        print("\nRe-run with --install to install it into Blender.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
