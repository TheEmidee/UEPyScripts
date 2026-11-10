import argparse
import json
from pathlib import Path

import pytest

from tests.ugs.conftest import InMemoryStorage
from uepyscripts.internal.config import ConfigError
from uepyscripts.internal.workspace import Workspace, add_uproject_argument
from uepyscripts.tools.ugs.connection import NotNativeProjectError, S3Settings, add_publish_store_arguments, open_publish_store
from uepyscripts.tools.ugs.publish_store import DEFAULT_JOBS
from uepyscripts.tools.ugs.storage import Storage

FULL_SECTION = """[UGS.AWS]
AWS_BucketName = config-bucket
AWS_Region = eu-west-3
AWS_AccessKey = config-access
AWS_SecretKey = config-secret
"""


class RecordingConnect:
    """Stands in for S3: remembers the settings it was given and hands back an in-memory storage."""

    def __init__(self) -> None:
        self.settings: list[S3Settings] = []
        self.storage = InMemoryStorage()

    def __call__(self, settings: S3Settings) -> Storage:
        self.settings.append(settings)
        return self.storage


def make_workspace(tmp_path: Path, ini: str | None = None, engine_association: str = "") -> Workspace:
    game = tmp_path / "Game"
    game.mkdir()
    uproject = game / "Game.uproject"
    uproject.write_text(json.dumps({"EngineAssociation": engine_association}))
    if ini is not None:
        config_folder = game / "Config" / "PyScripts"
        config_folder.mkdir(parents=True)
        (config_folder / "config.ini").write_text(ini)
    return Workspace(uproject)


def parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_uproject_argument(parser)
    add_publish_store_arguments(parser)
    return parser.parse_args(list(argv))


def test_a_project_that_is_not_native_is_refused_before_any_setting_is_read(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path, ini="[UGS.AWS]\nAWS_BucketName =\n", engine_association="5.4")
    connect = RecordingConnect()

    with pytest.raises(NotNativeProjectError):
        open_publish_store(workspace, parse(), connect=connect)

    assert connect.settings == []


def test_every_missing_value_is_reported_together_with_its_key_and_flag(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path, ini="[UGS.AWS]\nAWS_BucketName = config-bucket\n")
    connect = RecordingConnect()

    with pytest.raises(ConfigError) as error:
        open_publish_store(workspace, parse("--s3-access-key", "cli-access"), connect=connect)

    assert error.value.section == "UGS.AWS"
    assert error.value.problems == [
        "AWS_Region: missing (or pass --s3-bucket-region)",
        "AWS_SecretKey: missing (or pass --s3-secret-key)",
    ]
    assert connect.settings == []


def test_the_project_config_alone_is_enough(tmp_path: Path) -> None:
    connect = RecordingConnect()

    open_publish_store(make_workspace(tmp_path, ini=FULL_SECTION), parse(), connect=connect)

    assert connect.settings == [S3Settings("config-bucket", "eu-west-3", "config-access", "config-secret")]


def test_each_flag_overrides_its_config_value(tmp_path: Path) -> None:
    connect = RecordingConnect()

    open_publish_store(
        make_workspace(tmp_path, ini=FULL_SECTION), parse("--s3-bucket-name", "cli-bucket", "--s3-secret-key", "cli-secret"), connect=connect
    )

    assert connect.settings == [S3Settings("cli-bucket", "eu-west-3", "config-access", "cli-secret")]


def test_flags_alone_are_enough_without_any_project_config(tmp_path: Path) -> None:
    connect = RecordingConnect()
    args = parse("--s3-bucket-name", "b", "--s3-bucket-region", "r", "--s3-access-key", "a", "--s3-secret-key", "s")

    open_publish_store(make_workspace(tmp_path), args, connect=connect)

    assert connect.settings == [S3Settings("b", "r", "a", "s")]


def test_jobs_reach_the_store(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path, ini=FULL_SECTION)

    assert open_publish_store(workspace, parse(), connect=RecordingConnect()).jobs == DEFAULT_JOBS
    assert open_publish_store(workspace, parse("--jobs", "4"), connect=RecordingConnect()).jobs == 4


def test_a_dry_run_never_writes_to_the_storage(tmp_path: Path) -> None:
    connect = RecordingConnect()

    store = open_publish_store(make_workspace(tmp_path, ini=FULL_SECTION), parse(), dry_run=True, connect=connect)
    store.save_symstore_manifest({"Bin/a.dll": "hash"})

    assert connect.storage.objects == {}
