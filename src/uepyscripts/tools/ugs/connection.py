"""
Opening the Publish store from a Workspace, for the commands that publish,
sync or clean up binaries.

`add_publish_store_arguments` registers the command line arguments and
`open_publish_store` reads them back. The S3 connection info comes from the
[UGS.AWS] Config section, and each value can be overridden by its `--s3-*`
argument. Having no Project config at all is fine when the command line gives
everything, but every value missing from both is reported together, before
anything connects to S3.

Failures are WorkspaceErrors, so `open_workspace` reports them like any other
problem with the Workspace.
"""

import argparse
from collections.abc import Callable
from dataclasses import dataclass

from gamedevtools.s3 import S3Client

from uepyscripts.internal.config import ConfigError, UgsAwsSection
from uepyscripts.internal.errors import WorkspaceError
from uepyscripts.internal.workspace import Workspace
from uepyscripts.tools.ugs.publish_store import DEFAULT_JOBS, PublishStore
from uepyscripts.tools.ugs.storage import DryRunStorage, S3Storage, Storage

S3_CONFIG_SECTION = UgsAwsSection.section_name


class NotNativeProjectError(WorkspaceError):
    """Binaries are only published and synced for a Native project."""


@dataclass(frozen=True)
class S3Settings:
    bucket_name: str
    bucket_region: str
    access_key: str
    secret_key: str


def connect_to_s3(settings: S3Settings) -> Storage:
    client = S3Client(access_key=settings.access_key, secret_key=settings.secret_key, region=settings.bucket_region)
    return S3Storage(client, settings.bucket_name)


def add_publish_store_arguments(parser: argparse.ArgumentParser) -> None:
    """Registers `--jobs` and one `--s3-*` argument per key of the [UGS.AWS] Config section."""
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help=f"Parallel transfers with the Publish store (default: {DEFAULT_JOBS})")

    group = parser.add_argument_group("AWS S3", f"Each one overrides its key in the [{S3_CONFIG_SECTION}] section of the Project config")
    for name, info in UgsAwsSection.model_fields.items():
        group.add_argument(_flag(name), type=str, help=f"(config: {info.alias})")


def open_publish_store(
    workspace: Workspace,
    args: argparse.Namespace,
    *,
    dry_run: bool = False,
    connect: Callable[[S3Settings], Storage] = connect_to_s3,
) -> PublishStore:
    """The Publish store, from the parsed arguments of `add_publish_store_arguments`.

    Raises NotNativeProjectError for a project that is not Native, and a
    ConfigError listing every S3 value missing from both the command line and
    the Project config. With `dry_run`, writes and deletes are only logged."""
    if not workspace.project.is_native_project:
        raise NotNativeProjectError(
            f"Binaries can only be published and synced for a Native project, and {workspace.project.project_name} is not one"
        )

    section = workspace.config.ugs_aws
    values: dict[str, str] = {}
    missing: list[str] = []
    for name, info in UgsAwsSection.model_fields.items():
        value = getattr(args, _dest(name), None) or getattr(section, name)
        if value:
            values[name] = value
        else:
            missing.append(f"{info.alias}: missing (or pass {_flag(name)})")

    if missing:
        raise ConfigError(S3_CONFIG_SECTION, missing, workspace.config.folder)

    storage = connect(S3Settings(**values))
    if dry_run:
        storage = DryRunStorage(storage)

    return PublishStore(storage, jobs=args.jobs)


def _flag(name: str) -> str:
    return f"--s3-{name.replace('_', '-')}"


def _dest(name: str) -> str:
    return f"s3_{name}"
