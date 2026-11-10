class WorkspaceError(Exception):
    """Base class for everything that can go wrong while resolving a Workspace:
    its project, its Project config or its engine. The command line edge
    (workspace.open_workspace) turns any of them into a fatal log and exit code."""
