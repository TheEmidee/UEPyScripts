from pathlib import Path

import pytest

from uepyscripts.internal.config import Config, ConfigError
from uepyscripts.internal.errors import WorkspaceError


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "Game"
    root.mkdir()
    return root


def config_folder(project_root: Path) -> Path:
    return project_root / "Config" / "PyScripts"


def write_ini(project_root: Path, text: str, name: str = "config.ini") -> None:
    folder = config_folder(project_root)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text)


def load(project_root: Path) -> Config:
    return Config(config_folder(project_root), project_root)


def test_project_section_reads_typed_values(project_root: Path, tmp_path: Path) -> None:
    write_ini(
        project_root,
        f"""
[Project]
BuildgraphPath = Build/Graph.xml
AutomationScriptsDirectories = Build/Scripts + {tmp_path / "Shared"} +
BuildgraphSharedProperties = Clean=True+ Targets = Client
""",
    )

    project = load(project_root).project

    assert project.buildgraph_path == (project_root / "Build" / "Graph.xml").resolve()
    assert project.automation_scripts_directories == [(project_root / "Build" / "Scripts").resolve(), tmp_path / "Shared"]
    assert project.buildgraph_shared_properties == {"Clean": "True", "Targets": "Client"}


def test_jenkins_section_reads_a_unc_path(project_root: Path) -> None:
    write_ini(project_root, "[Jenkins]\nBuildgraphSharedStoragePath = \\\\nas\\cache\\UE-BuildGraph\n")

    storage = load(project_root).jenkins.buildgraph_shared_storage_path

    assert storage / "tag" == Path(r"\\nas\cache\UE-BuildGraph\tag")


def test_ugs_aws_section_reads_optional_keys(project_root: Path) -> None:
    write_ini(project_root, "[UGS.AWS]\nAWS_BucketName = bucket\nAWS_Region = eu-west-1\n")

    ugs_aws = load(project_root).ugs_aws

    assert (ugs_aws.bucket_name, ugs_aws.bucket_region, ugs_aws.access_key, ugs_aws.secret_key) == ("bucket", "eu-west-1", None, None)


def test_property_values_keep_everything_after_the_first_equals(project_root: Path) -> None:
    write_ini(project_root, "[Project]\nBuildgraphSharedProperties = Args=-a=1 -b=2+Empty=\n")

    assert load(project_root).project.buildgraph_shared_properties == {"Args": "-a=1 -b=2", "Empty": ""}


def test_missing_folder_is_an_empty_project_config(project_root: Path) -> None:
    config = load(project_root)

    assert config.project.buildgraph_path is None
    assert config.project.automation_scripts_directories == []
    assert config.ugs_aws.bucket_name is None

    with pytest.raises(ConfigError) as error:
        _ = config.jenkins

    assert str(config_folder(project_root)) in str(error.value)
    assert isinstance(error.value, WorkspaceError)


def test_empty_value_counts_as_missing(project_root: Path) -> None:
    write_ini(project_root, "[Jenkins]\nBuildgraphSharedStoragePath =\n[Project]\nBuildgraphPath =\n")
    config = load(project_root)

    assert config.project.buildgraph_path is None
    with pytest.raises(ConfigError) as error:
        _ = config.jenkins

    assert error.value.problems == ["BuildgraphSharedStoragePath: missing"]


def test_every_problem_in_a_section_is_reported_together(project_root: Path) -> None:
    write_ini(project_root, "[Project]\nBuildgraphSharedProperties = Clean=True+NoEquals+=Value\n")

    with pytest.raises(ConfigError) as error:
        _ = load(project_root).project

    assert error.value.section == "Project"
    assert len(error.value.problems) == 1
    assert "BuildgraphSharedProperties" in error.value.problems[0]
    assert "NoEquals" in error.value.problems[0]
    assert "'=Value'" in error.value.problems[0]


def test_ini_files_merge_in_file_name_order(project_root: Path) -> None:
    write_ini(project_root, "[Jenkins]\nBuildgraphSharedStoragePath = C:/Second\n", name="b_overrides.ini")
    write_ini(project_root, "[Jenkins]\nBuildgraphSharedStoragePath = C:/First\n[Project]\nBuildgraphPath = Graph.xml\n", name="a_base.ini")

    config = load(project_root)

    assert config.jenkins.buildgraph_shared_storage_path == Path("C:/Second")
    assert config.project.buildgraph_path == (project_root / "Graph.xml").resolve()


def test_unknown_sections_and_keys_are_ignored(project_root: Path) -> None:
    write_ini(project_root, "[Somebody.Else]\nAnything = 1\n[Jenkins]\nBuildgraphSharedStoragePath = C:/Storage\nUnknownKey = 2\n")

    assert load(project_root).jenkins.buildgraph_shared_storage_path == Path("C:/Storage")


def test_keys_are_case_insensitive(project_root: Path) -> None:
    write_ini(project_root, "[Jenkins]\nbuildgraphsharedstoragepath = C:/Storage\n")

    assert load(project_root).jenkins.buildgraph_shared_storage_path == Path("C:/Storage")


def test_a_section_read_is_cached(project_root: Path) -> None:
    write_ini(project_root, "[Jenkins]\nBuildgraphSharedStoragePath = C:/Storage\n")
    config = load(project_root)

    assert config.jenkins is config.jenkins
