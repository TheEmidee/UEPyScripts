import json
from pathlib import Path

import pytest

from tests.fakes import write_build_version


@pytest.fixture
def game(tmp_path: Path) -> Path:
    """A Native project in tmp_path/Game, with its engine at tmp_path. Its Shared storage folder is tmp_path/Storage."""
    write_build_version(tmp_path)
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
