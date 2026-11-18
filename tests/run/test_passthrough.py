from pathlib import Path
from types import ModuleType

import pytest

from tests.fakes import RecordingRunner, tool, write_build_version, write_uproject
from uepyscripts.run import uat, ubt

TOOL_PARTS = {
    uat: ("Build", "BatchFiles", "RunUAT.bat"),
    ubt: ("Binaries", "DotNET", "UnrealBuildTool", "UnrealBuildTool.exe"),
}


@pytest.fixture
def uproject(tmp_path: Path) -> Path:
    """A Native project in tmp_path/Game, with its engine at tmp_path."""
    write_build_version(tmp_path)
    return write_uproject(tmp_path / "Game")


def forwarded(module: ModuleType, runner: RecordingRunner, uproject: Path) -> list[str]:
    """The arguments the command forwarded to its Engine tool, after the ones the Engine adds itself."""
    [argv] = runner.ran
    expected_prefix = [tool(uproject.parent.parent, *TOOL_PARTS[module])]
    if module is ubt:
        expected_prefix.append(str(uproject.resolve()))

    assert argv[: len(expected_prefix)] == expected_prefix
    return argv[len(expected_prefix) :]


@pytest.mark.parametrize("module", [uat, ubt])
@pytest.mark.parametrize("help_flag", ["-help", "-h", "--help", "-hotreload"])
def test_help_like_arguments_are_forwarded(module: ModuleType, help_flag: str, uproject: Path) -> None:
    runner = RecordingRunner(exit_code=7)

    exit_code = module.main([help_flag, f"--uproject-path={uproject}"], runner=runner)

    assert exit_code == 7
    assert forwarded(module, runner, uproject) == [help_flag]


@pytest.mark.parametrize("module", [uat, ubt])
def test_uproject_path_is_consumed_and_the_rest_forwarded_in_order(module: ModuleType, uproject: Path) -> None:
    runner = RecordingRunner()

    module.main(["turnkey", "--uproject-path", str(uproject), "-command=VerifySdk", "-help"], runner=runner)

    assert forwarded(module, runner, uproject) == ["turnkey", "-command=VerifySdk", "-help"]
