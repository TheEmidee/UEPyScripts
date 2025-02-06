from uepyscripts.internal.project import Project
from pathlib import Path
from uepyscripts import logger

import os
import configparser

class Config:
    def __init__(self, folder : Path):
        self.folder = folder
        self.config = configparser.ConfigParser()

        logger.debug("Initializing config")

        ini_files = [f for f in os.listdir(self.folder) if f.endswith('.ini')]
        
        for ini_file in ini_files:
            ini_path = os.path.join(self.folder, ini_file)
            logger.debug(f"Reading file: {ini_path}")
            self.config.read(ini_path)

    def __getitem__(self, key):
        return self.config[key]

def resolve_config(project : Project) -> Config:
    config_folder = project.project_folders.config.joinpath("PyScripts")

    if not config_folder.exists():
        raise Exception("Impossible to find the PyScripts folder in Config")
    
    return Config(config_folder)