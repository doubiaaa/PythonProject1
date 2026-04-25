from __future__ import annotations

import re
import shutil
from pathlib import Path
from uuid import uuid4

import pytest


def _tmp_root() -> Path:
    root = Path(__file__).resolve().parent.parent / "test_tmp"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Path:
    # Keep scratch space inside the repo to avoid Python 3.14/Windows tmpdir
    # permission issues observed in the current sandbox.
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.name).strip("._")
    target = _tmp_root() / f"{safe_name or 'tmp'}_{uuid4().hex[:8]}"
    target.mkdir(parents=True, exist_ok=False)
    try:
        yield target
    finally:
        shutil.rmtree(target, ignore_errors=True)
