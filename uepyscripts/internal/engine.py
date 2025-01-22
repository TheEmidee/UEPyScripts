from uepyscripts import logger
from uepyscripts.internal.project import Project
from pathlib import Path
from packaging.version import Version

import json
import os
import re
import winreg 

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
    
def resolve_engine_from_env_var(project: Project) -> Path:
    key = "NODE_UE_ROOT"
    
    if key in os.environ:
        node_ue_root = os.environ[key]
        if node_ue_root:
            path = Path(path)
            if path.exists():
                path = path.joinpath(project.engine_association)
                if path.exists():
                    return path
                
                raise Exception(f"The environment variable {key} is set to {node_ue_root} but no engine folder named {project.engine_association} exists")
            
            raise Exception(f"The environment variable {key} is set to {node_ue_root} but this folder does not exist")

    return None

def get_registry_value(
        hkey : int,
        key_path : str,
        value_name : str
    ) -> Path:
    full_path = f"{key_path}\\{value_name}"

    try:
        with winreg.OpenKey(hkey,key_path) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
            return Path(value)
    except FileNotFoundError:
        logger.debug(f"No string value in the registry for the key {full_path}")
    except Exception as e:
        logger.fatal(f"An error occurred when trying to read {full_path}: {e}")
        return None
    
def resolve_engine_from_registry(project: Project) -> Path:
    result = get_registry_value(winreg.HKEY_CURRENT_USER,r"SOFTWARE\Epic Games\Unreal Engine\Builds",project.engine_association)
    if not result:
        result = get_registry_value(winreg.HKEY_LOCAL_MACHINE,fr"SOFTWARE\EpicGames\Unreal Engine\{project.engine_association}","InstalledDirectory")

    return result

def resolve_engine_from_program_files(project: Project) -> Path:
    if re.search(r"^[45]\.[0-9]+(EA)?$", project.engine_association):
        path = fr"{os.environ["PROGRAMFILES"]}\Epic Games\{project.engine_association}"
        if os.path.exists(path):
            return Path(path)

    return None

def resolve_engine_from_path(project: Project) -> Path:
    path = Path(project.engine_association)
    if os.path.isabs(path):
        return path
    
    return None

def resolve_engine_path(project: Project) -> Path:
    resolvers = [
        resolve_engine_from_env_var,
        resolve_engine_from_registry,
        resolve_engine_from_program_files,
        resolve_engine_from_path,
    ]

    for resolver in resolvers:
        path = resolver(project)
        if path:
            break
    else:
        raise Exception("Impossible to locate the engine")

    if not ( path.exists() and str(path).replace(" ", "") not in ["", ".", "\\"] ):
        raise Exception("Impossible to locate the engine")
    
    return path

def resolve_engine(project: Project) -> Engine:
    engine = Engine(resolve_engine_path(project))
    logger.info(engine)
    return engine

def get_engine() -> Engine:
    from uepyscripts.internal.project import resolve_project
    
    project = resolve_project()
    return resolve_engine(project)