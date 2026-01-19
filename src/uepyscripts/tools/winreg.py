import winreg
from pathlib import Path

from uepyscripts import logger


def get_registry_value(hkey: int, key_path: str, value_name: str) -> Path:
    full_path = f"{key_path}\\{value_name}"

    try:
        with winreg.OpenKey(hkey, key_path) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
            return Path(value)
    except FileNotFoundError:
        logger.debug(f"No string value in the registry for the key {full_path}")
    except Exception as e:
        logger.fatal(f"An error occurred when trying to read {full_path}: {e}")
        return None


def write_registry_value(hkey: int, key_path: str, value_name: str, value_data: str) -> bool:
    full_path = f"{key_path}\\{value_name}"

    try:
        with winreg.CreateKey(hkey, key_path) as key:
            winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, value_data)
            return True
    except Exception as e:
        logger.fatal(f"An error occurred when trying to write {full_path}: {e}")
        return False
