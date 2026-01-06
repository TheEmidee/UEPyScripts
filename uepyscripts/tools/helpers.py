import os
from pathlib import Path
import re
import winreg 

from uepyscripts import logger

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
    
def is_engine_from_egs(engine_version: str) -> bool:
    return re.search(r"^[45]\.[0-9]+(EA)?$", engine_version)

def get_env_var_value() -> str:
    key = "NODE_UE_ROOT"
    
    if key in os.environ:
        return os.environ[key]
    
    return None

def get_engine_root_folder_from_env_var(project_engine_association: str = None) -> Path:
    node_ue_root = get_env_var_value()
    
    if node_ue_root:
        path = Path(node_ue_root)
        if project_engine_association:
            path = path.joinpath(project_engine_association)
        if path.exists():
            return path
    
        raise FileNotFoundError(f"The environment variable is set to {node_ue_root} but the folder {path} does not exist")
        
    return None