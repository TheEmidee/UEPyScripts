import os
import re
from pathlib import Path
from typing import Optional


def is_engine_from_egs(engine_version: str) -> bool:
    return re.search(r"^[45]\.[0-9]+(EA)?$", engine_version) is not None


def get_env_var_value() -> Optional[str]:
    key = "NODE_UE_ROOT"

    if key in os.environ:
        return os.environ[key]

    return None


def get_engine_root_folder_from_env_var(project_engine_association: str) -> Optional[Path]:
    node_ue_root = get_env_var_value()

    if node_ue_root:
        path = Path(node_ue_root)
        if project_engine_association:
            path = path.joinpath(project_engine_association)
        return path

    return None
