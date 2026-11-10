"""
The BuildGraph command: one UAT BuildGraph invocation, built from structured
inputs instead of argv strings.

`BuildGraphCommand.uat_arguments()` is pure. `BuildGraphCommand.for_workspace`
fills in what comes from the Workspace (the script, the project, script
folders and shared properties from the Project config) and validates it.

There is a single override rule: an extra argument whose key matches a
generated one drops the generated one. A key is the argument up to its first
`=` or `:`, compared case-insensitively, except `-set:Name=Value`, whose key
is the property name.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from uepyscripts import logger
from uepyscripts.internal.config import ConfigError
from uepyscripts.internal.errors import WorkspaceError
from uepyscripts.internal.workspace import Workspace

SET_PREFIX = "-set:"


class BuildGraphError(WorkspaceError):
    """The BuildGraph command can't be built: a bad script, or not exactly one of target and Single node."""


def argument_key(argument: str) -> str:
    """The key used by the override rule: `-Key`, `-Key=…` and `-Key:…` share the key `-key`,
    and `-set:Name=Value` has the key `-set:name`."""
    lowered = argument.lower()
    if lowered.startswith(SET_PREFIX):
        return lowered.split("=", 1)[0]

    return lowered.split("=", 1)[0].split(":", 1)[0]


@dataclass(frozen=True)
class BuildGraphCommand:
    script: Path
    uproject_path: Path
    target: Optional[str] = None
    single_node: Optional[str] = None
    script_dirs: list[Path] = field(default_factory=list)
    properties: dict[str, str] = field(default_factory=dict)
    build_machine: bool = False
    no_p4: bool = False
    shared_storage: Optional[Path] = None
    write_to_shared_storage: bool = False
    extra_args: list[str] = field(default_factory=list)

    def uat_arguments(self) -> list[str]:
        """The arguments to pass to UAT, starting with `BuildGraph`."""
        generated = [f"-script={self.script}"]
        generated.append(f"-target={self.target}" if self.target else f"-SingleNode={self.single_node}")
        generated.append(f"-Project={self.uproject_path}")
        generated += [f"-ScriptDir={script_dir}" for script_dir in self.script_dirs]
        generated += [f"{SET_PREFIX}{name}={value}" for name, value in self.properties.items()]

        if self.build_machine:
            generated.append("-BuildMachine")
        if self.no_p4:
            generated.append("-NoP4")
        if self.shared_storage:
            generated.append(f"-SharedStorageDir={self.shared_storage}")
        if self.write_to_shared_storage:
            generated.append("-WriteToSharedStorage")

        overridden = {argument_key(argument) for argument in self.extra_args}
        return ["BuildGraph", *(argument for argument in generated if argument_key(argument) not in overridden), *self.extra_args]

    @classmethod
    def for_workspace(
        cls,
        workspace: Workspace,
        *,
        target: Optional[str] = None,
        single_node: Optional[str] = None,
        script: Optional[Path] = None,
        extra_args: Sequence[str] = (),
        build_machine: bool = False,
        no_p4: bool = False,
        shared_storage: Optional[Path] = None,
        write_to_shared_storage: bool = False,
    ) -> "BuildGraphCommand":
        """Builds the command for the Workspace's project.

        The script is `script`, or else `[Project] BuildgraphPath`. Script folders
        that don't exist are skipped with a warning. `-set:Name=Value` extra
        arguments are merged over `[Project] BuildgraphSharedProperties`, the
        command line winning, so each property is passed once."""
        if bool(target) == bool(single_node):
            raise BuildGraphError("Pass exactly one of a target and a Single node")

        project_section = workspace.config.project
        script_path = cls._resolve_script(workspace, script)

        script_dirs: list[Path] = []
        for script_dir in project_section.automation_scripts_directories:
            if not script_dir.exists():
                logger.warning(f"The automation scripts directory does not exist. Current value {script_dir}")
                continue

            logger.info(f"Automation Scripts directory set to {script_dir}")
            script_dirs.append(script_dir)

        if not project_section.automation_scripts_directories:
            logger.info("No automation scripts directory is set")

        properties = dict(project_section.buildgraph_shared_properties)
        remaining_args: list[str] = []
        for argument in extra_args:
            if argument.lower().startswith(SET_PREFIX):
                name, _, value = argument[len(SET_PREFIX) :].partition("=")
                properties[name] = value
            else:
                remaining_args.append(argument)

        if not properties:
            logger.info("No shared properties to set")

        return cls(
            script=script_path,
            uproject_path=workspace.project.uproject_path,
            target=target,
            single_node=single_node,
            script_dirs=script_dirs,
            properties=properties,
            build_machine=build_machine,
            no_p4=no_p4,
            shared_storage=shared_storage,
            write_to_shared_storage=write_to_shared_storage,
            extra_args=remaining_args,
        )

    @staticmethod
    def _resolve_script(workspace: Workspace, script: Optional[Path]) -> Path:
        config = workspace.config
        if script:
            script_path = script
        elif config.project.buildgraph_path:
            script_path = config.project.buildgraph_path
        else:
            raise ConfigError("Project", ["BuildgraphPath: missing (or pass --script)"], config.folder)

        logger.info(f"Buildgraph XML path : {script_path}")

        if not script_path.exists():
            raise BuildGraphError(f"The BuildGraph script does not exist: {script_path}")
        if script_path.suffix.lower() != ".xml":
            raise BuildGraphError(f"The BuildGraph script must be an XML file: {script_path}")

        return script_path
