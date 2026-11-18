from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from uepyscripts.internal.errors import InvalidProjectError, describe_json_problems


class ProjectSavedFolders:
    def __init__(self, saved_folder: Path) -> None:
        self.buildgraph = saved_folder.joinpath("BuildGraph")
        self.jenkins = saved_folder.joinpath("Jenkins")
        self.temp = saved_folder.joinpath("Temp")
        self.tests = saved_folder.joinpath("Tests")
        self.local_builds = saved_folder.joinpath("LocalBuilds")
        self.staged_builds = saved_folder.joinpath("StagedBuilds")


class ProjectFolders:
    def __init__(self, root_folder: Path) -> None:
        self.config = root_folder.joinpath("Config")
        self.saved = root_folder.joinpath("Saved")
        self.saved_folders = ProjectSavedFolders(self.saved)


class UProjectFile(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    engine_association: str = Field(alias="EngineAssociation")


class Project:
    def __init__(self, uproject_path: Path) -> None:
        self.uproject_path = uproject_path.resolve()
        self.project_name = uproject_path.stem
        self.root_folder = uproject_path.parent
        self.project_folders = ProjectFolders(self.root_folder)

        try:
            self.uproject = UProjectFile.model_validate_json(self.uproject_path.read_text(encoding="utf-8"))
        except OSError as e:
            raise InvalidProjectError(f"Could not read {self.uproject_path}: {e}") from e
        except ValidationError as e:
            raise InvalidProjectError(f"Invalid uproject {self.uproject_path}: {describe_json_problems(e)}") from e

    @property
    def engine_association(self) -> str:
        return self.uproject.engine_association

    @property
    def is_native_project(self) -> bool:
        return not self.engine_association

    def __str__(self) -> str:
        return f"""
----- Project infos -----
* Folder : {self.root_folder}
* ProjectName : {self.project_name}
* UProjectPath : {self.uproject_path}
* EngineAssociation : {self.engine_association}
----- Project infos -----
        """


EXCLUDED_DIR_NAMES = {"Engine", "FeaturePacks", "Samples", "Scripts", "Templates", ".git"}


def find_uproject_in_subfolders(root: Path) -> Optional[Path]:
    """Recursively search for a .uproject file under root, skipping excluded folders."""
    for entry in root.iterdir():
        if entry.is_dir():
            if entry.name in EXCLUDED_DIR_NAMES:
                continue
            found = find_uproject_in_subfolders(entry)
            if found:
                return found
        elif entry.is_file() and entry.suffix == ".uproject":
            return entry.resolve()

    return None


def find_parent_with_project_file(starting_path: Path, max_parents: int = 10) -> Optional[Path]:
    current_path = Path(starting_path).resolve()

    search_paths = [current_path, *current_path.parents[:max_parents]]

    for path in search_paths:
        for file in path.iterdir():
            if file.is_file() and file.suffix == ".uproject":
                return file.resolve()

        build_version_path = path / "Engine" / "Build" / "Build.version"
        if build_version_path.is_file():
            return find_uproject_in_subfolders(path)

    return None
