from uepyscripts import logger
from uepyscripts.internal.project import Project
from pathlib import Path

import os
import re
import winreg 

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
        program_files_path = os.environ["PROGRAMFILES"]
        path = fr"{program_files_path}\Epic Games\{project.engine_association}"
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