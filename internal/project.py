from .. import logger
from pathlib import Path
import json
import os 

class ProjectSavedFolders:
    buildgraph : Path
    jenkins : Path
    temp : Path
    tests : Path
    local_builds : Path
    staged_builds : Path

    def __init__(self, saved_folder : Path):
        self.buildgraph = saved_folder.joinpath("BuildGraph")
        self.jenkins = saved_folder.joinpath("Jenkins")
        self.temp = saved_folder.joinpath("Temp")
        self.tests = saved_folder.joinpath("Tests")
        self.local_builds = saved_folder.joinpath("LocalBuilds")
        self.staged_builds = saved_folder.joinpath("StagedBuilds")

class ProjectFolders:
    config : Path
    saved : Path
    saved_folder : ProjectSavedFolders

    def __init__(self, root_folder : Path):
        self.config = root_folder.joinpath("Config")
        self.saved = root_folder.joinpath("Saved")
        self.saved_folders = ProjectSavedFolders(self.saved)

class Project:
    root_folder : Path
    project_name : str
    uproject_path : Path
    project_folders : ProjectFolders
    engine_association : str

    def __init__(self, uproject_path : Path):
        self.uproject_path = uproject_path.resolve()
        self.project_name = uproject_path.stem
        self.root_folder = uproject_path.parent
        self.project_folders = ProjectFolders(self.root_folder)

        with open(self.uproject_path, 'r') as f:
            uproject_json = json.load(f)
            self.engine_association = uproject_json["EngineAssociation"]        

    def __str__(self):
        return f"""
----- Project infos -----
* Folder : {self.root_folder}
* ProjectName : {self.project_name}
* UProjectPath : {self.uproject_path}
* EngineAssociation : {self.engine_association}
----- Project infos -----
        """

def find_parent_with_project_file(
    starting_path : Path,
    max_parents : int =5
    ):
    current_path = Path(starting_path).resolve()

    search_paths = [current_path, *current_path.parents[:max_parents]]
    
    for path in search_paths:
        for file in path.iterdir():
            if file.is_file() and file.suffix == ".uproject":
                return file.resolve()
    
    return None

def resolve_project() -> Project :
    dir_path = os.path.dirname(os.path.realpath(__file__))

    uproject_path = find_parent_with_project_file(dir_path)
    if not uproject_path:
        raise Exception("Could not find a uproject file")
    
    logger.debug(f"Found uproject file at {uproject_path}")
    project = Project(uproject_path)

    logger.info(project)
    return project