import json
from pathlib import Path

import pytest


@pytest.fixture
def game(tmp_path: Path) -> Path:
    """A Native project whose Shared storage folder is tmp_path/Storage."""
    game = tmp_path / "Game"
    (game / "Build").mkdir(parents=True)
    (game / "Build" / "Graph.xml").write_text("<BuildGraph/>")
    (game / "Game.uproject").write_text(json.dumps({"EngineAssociation": ""}))
    config = game / "Config" / "PyScripts"
    config.mkdir(parents=True)
    (config / "config.ini").write_text(
        f"[Project]\nBuildgraphPath = Build/Graph.xml\n[Jenkins]\nBuildgraphSharedStoragePath = {tmp_path / 'Storage'}\n"
    )
    return game
