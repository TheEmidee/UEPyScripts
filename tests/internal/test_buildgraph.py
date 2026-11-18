import json
from pathlib import Path

import pytest

from uepyscripts.internal.buildgraph import BuildGraphCommand, BuildGraphError, SingleNode, Target
from uepyscripts.internal.config import ConfigError
from uepyscripts.internal.workspace import Workspace

SCRIPT = Path("C:/Game/Build/Graph.xml")
UPROJECT = Path("C:/Game/Game.uproject")


def make_workspace(tmp_path: Path, ini: str = "", script: bool = True) -> Workspace:
    game = tmp_path / "Game"
    game.mkdir()
    (game / "Game.uproject").write_text(json.dumps({"EngineAssociation": ""}))
    if script:
        (game / "Build").mkdir()
        (game / "Build" / "Graph.xml").write_text("<BuildGraph/>")
    if ini:
        config = game / "Config" / "PyScripts"
        config.mkdir(parents=True)
        (config / "config.ini").write_text(ini)
    return Workspace(game / "Game.uproject")


def test_arguments_for_a_target_in_order() -> None:
    command = BuildGraphCommand(
        script=SCRIPT,
        uproject_path=UPROJECT,
        run=Target("Compile"),
        script_dirs=[Path("C:/Scripts")],
        properties={"Clean": "True", "Targets": "Client+Server"},
        extra_args=["-verbose"],
    )

    assert command.uat_arguments() == [
        "BuildGraph",
        f"-script={SCRIPT}",
        "-target=Compile",
        f"-Project={UPROJECT}",
        f"-ScriptDir={Path('C:/Scripts')}",
        "-set:Clean=True",
        "-set:Targets=Client+Server",
        "-verbose",
    ]


def test_arguments_for_a_single_node_on_a_build_machine() -> None:
    command = BuildGraphCommand(
        script=SCRIPT,
        uproject_path=UPROJECT,
        run=SingleNode("Compile Win64", Path("//nas/storage/tag")),
        build_machine=True,
    )

    assert command.uat_arguments() == [
        "BuildGraph",
        f"-script={SCRIPT}",
        "-SingleNode=Compile Win64",
        f"-Project={UPROJECT}",
        "-BuildMachine",
        "-NoP4",
        f"-SharedStorageDir={Path('//nas/storage/tag')}",
        "-WriteToSharedStorage",
    ]


def test_extra_arguments_replace_generated_ones_with_the_same_key() -> None:
    command = BuildGraphCommand(
        script=SCRIPT,
        uproject_path=UPROJECT,
        run=SingleNode("Node", Path("C:/Storage")),
        properties={"Clean": "True", "Targets": "Client"},
        build_machine=True,
        extra_args=["-project=D:/Other.uproject", "-nop4", "-SharedStorageDir:D:/Elsewhere", "-set:clean=False"],
    )

    assert command.uat_arguments() == [
        "BuildGraph",
        f"-script={SCRIPT}",
        "-SingleNode=Node",
        "-set:Targets=Client",
        "-BuildMachine",
        "-WriteToSharedStorage",
        "-project=D:/Other.uproject",
        "-nop4",
        "-SharedStorageDir:D:/Elsewhere",
        "-set:clean=False",
    ]


def test_factory_reads_the_script_script_dirs_and_properties_from_config(tmp_path: Path) -> None:
    workspace = make_workspace(
        tmp_path,
        "[Project]\nBuildgraphPath = Build/Graph.xml\nAutomationScriptsDirectories = Build/Scripts+Build/Missing\n"
        "BuildgraphSharedProperties = Clean=False+Targets=Client\n",
    )
    (tmp_path / "Game" / "Build" / "Scripts").mkdir()

    command = BuildGraphCommand.for_workspace(workspace, Target("Compile"), extra_args=["-set:Clean=True", "-set:Extra=1", "-verbose"])

    assert command.script == (tmp_path / "Game" / "Build" / "Graph.xml").resolve()
    assert command.uproject_path == workspace.project.uproject_path
    assert command.script_dirs == [(tmp_path / "Game" / "Build" / "Scripts").resolve()]
    assert command.properties == {"Clean": "False", "Targets": "Client"}
    assert command.extra_args == ["-set:Clean=True", "-set:Extra=1", "-verbose"]


def test_a_command_line_property_replaces_the_config_one_whatever_its_case(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path, "[Project]\nBuildgraphPath = Build/Graph.xml\nBuildgraphSharedProperties = Clean=True+Targets=Client\n")

    arguments = BuildGraphCommand.for_workspace(workspace, Target("Compile"), extra_args=["-set:clean=False"]).uat_arguments()

    assert [argument for argument in arguments if argument.lower().startswith("-set:")] == ["-set:Targets=Client", "-set:clean=False"]


def test_factory_prefers_the_explicit_script(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path, "[Project]\nBuildgraphPath = Missing.xml\n")
    explicit = tmp_path / "Game" / "Build" / "Graph.xml"

    assert BuildGraphCommand.for_workspace(workspace, Target("T"), script=explicit).script == explicit


def test_factory_without_any_script_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        BuildGraphCommand.for_workspace(make_workspace(tmp_path), Target("T"))


@pytest.mark.parametrize("script_name", ["Missing.xml", "Graph.txt"])
def test_factory_rejects_a_missing_or_non_xml_script(tmp_path: Path, script_name: str) -> None:
    workspace = make_workspace(tmp_path)
    script = tmp_path / "Game" / script_name
    if script_name.endswith(".txt"):
        script.write_text("")

    with pytest.raises(BuildGraphError):
        BuildGraphCommand.for_workspace(workspace, Target("T"), script=script)
