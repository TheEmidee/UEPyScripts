from .. import logger
from .project import Project
from pathlib import Path
from packaging.version import Version
import json
import pathlib

class Engine:
    class Runner:
        path : Path

        def __init__(self, path : Path):
            if not path.exists():
                raise FileNotFoundError(f"The file {path} does not exist")
            
            self.path = path.resolve()

        def run(self, args : list[str] = {}):
            pass

    root_path : Path
    path : Path
    version : Version
    uat_path : Runner
    ubt_ath : Runner
    build_bat_path : Runner
    editor_exe_path : Runner
    
    def __init__(self, root_path:Path):
        self.root_path = root_path
        self.path = Path(root_path).joinpath("Engine").resolve()
        self.version = self.get_version_number()
        self.uat_path = self.Runner(self.path.joinpath("Build/BatchFiles/RunUAT.bat"))
        self.ubt_path = self.Runner(self.path.joinpath("Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.exe"))
        self.build_bat_path = self.Runner(self.path.joinpath("Build/BatchFiles/Build.bat"))
        self.editor_exe_path = self.Runner(self.path.joinpath("Binaries/Win64/UnrealEditor.exe"))

    def uat(self, args: list[str]):
        logger.info(f"UAT - {args}")

    def get_version_number(self) -> Version:
        version = ""
        
        with open(self.path.joinpath("Build/Build.version")) as build_version_file:
            version_json = json.load(build_version_file)
            major = version_json["MajorVersion"]
            minor = version_json["MinorVersion"]
            patch = version_json["PatchVersion"]
            version = f"{major}.{minor}.{patch}"

        if version == "":
            raise Exception("Impossible to find the version number of the engine")
        
        jenkins_file = Path(self.path.joinpath("Build/JenkinsBuild.version"))

        if jenkins_file.exists():        
            with open(jenkins_file) as jenkins_version_file:
                version += f".{jenkins_version_file.read()}"

        return Version(version)

    def __str__(self):
        return f"""
----- Engine infos -----
* Path : {self.path}
* Version : {self.version}
----- Engine infos -----
        """

def resolve_engine_path(project: Project) -> str:
    return pathlib.Path(__file__).parent.parent.parent

def resolve_engine(project: Project) -> Engine:
    engine = Engine(resolve_engine_path(project))
    logger.info(engine)
    return engine