import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from uepyscripts import logger


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

        with open(self.uproject_path, "r", encoding="utf-8") as f:
            json_str = f.read()
            self.uproject = UProjectFile.model_validate_json(json_str)

    @property
    def engine_association(self) -> str:
        return self.uproject.engine_association

    def __str__(self) -> str:
        return f"""
----- Project infos -----
* Folder : {self.root_folder}
* ProjectName : {self.project_name}
* UProjectPath : {self.uproject_path}
* EngineAssociation : {self.engine_association}
----- Project infos -----
        """


def find_parent_with_project_file(starting_path: Path, max_parents: int = 10) -> Optional[Path]:
    current_path = Path(starting_path).resolve()

    search_paths = [current_path, *current_path.parents[:max_parents]]

    for path in search_paths:
        for file in path.iterdir():
            if file.is_file() and file.suffix == ".uproject":
                return file.resolve()

    return None


def resolve_project(uproject_path: Path = None) -> Project:
    if not uproject_path:
        dir_path = Path(os.path.dirname(os.path.realpath(__file__)))
        uproject_path = find_parent_with_project_file(dir_path)
        if not uproject_path:
            raise Exception(f"Could not find a uproject file from {dir_path}")
    elif not uproject_path.exists():
        raise Exception(f"Could not find a uproject file from {dir_path}")

    logger.debug(f"Found uproject file at {uproject_path}")
    project = Project(uproject_path)

    logger.info(project)
    return project
