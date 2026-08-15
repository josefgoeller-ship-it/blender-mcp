import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# exec_core is written to run inside Blender, but the pure-data half of it is
# importable anywhere, so put its directory on the path for the unit tests.
sys.path.insert(0, str(PROJECT_ROOT / "addon" / "blender_mcp_addon"))


@pytest.fixture(autouse=True)
def restore_environment():
    """Undo any environment change a test makes.

    load_dotenv writes straight into os.environ, and monkeypatch.delenv(raising=False)
    records nothing when the variable was already absent, so leaks are easy otherwise.
    """
    snapshot = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(snapshot)


@pytest.fixture(scope="session")
def settings():
    from blender_mcp.config import BlenderNotFound, get_settings

    try:
        return get_settings()
    except BlenderNotFound as exc:
        pytest.skip(str(exc))
