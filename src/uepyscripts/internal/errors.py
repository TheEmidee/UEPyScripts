from pydantic import ValidationError


class WorkspaceError(Exception):
    """Base class for everything that can go wrong while resolving a Workspace:
    its project, its Project config or its engine. The command line edge
    (workspace.open_workspace) turns any of them into a fatal log and exit code."""


class ProjectNotFoundError(WorkspaceError):
    """No uproject was found by searching up from the current folder, or the given path isn't a file."""


class InvalidProjectError(WorkspaceError):
    """The uproject exists but can't be read, isn't valid JSON, or has no string EngineAssociation."""


class EngineNotFoundError(WorkspaceError):
    """The engine the project needs could not be located, or the folder found has no Engine/Build/Build.version."""


class InvalidEngineError(WorkspaceError):
    """The engine's Build.version or JenkinsBuild.version can't be read or doesn't give a version number."""


def describe_json_problems(error: ValidationError) -> str:
    """Every problem pydantic found in a JSON file, on one line."""
    problems = []
    for details in error.errors():
        if details["type"] == "json_invalid":
            problems.append(f"not valid JSON ({details['msg']})")
        else:
            key = ".".join(str(part) for part in details["loc"]) or "file"
            problems.append(f"{key}: {details['msg']}")

    return "; ".join(problems)
