from abc import ABC, abstractmethod
from pathlib import Path

import boto3

from .... import logger
from ....internal.project import Project
from ....internal.config import Config, resolve_config
from ....tools.helpers import is_engine_from_egs

class EngineSource(ABC):
    _registry = {}
    
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        name = cls.__name__.replace("EngineSource", "")
        cls._registry[name] = cls
    
    @classmethod
    def get_source(cls, name):
        return cls._registry.get(name)
    
    @classmethod
    @abstractmethod
    def can_use(cls, project: Project, config: Config) -> bool:
        pass

    @abstractmethod
    def copy_engine_to(self, destination: Path):
        pass

class EngineSourceEGS(EngineSource):
    @classmethod
    def can_use(cls, project: Project, config: Config) -> bool:
        return is_engine_from_egs(project.engine_association)
    
    def copy_engine_to(self, destination: Path):
        raise Exception("Engine installation via Epic Games Launcher is not supported. Please open the Epic Games Launcher and install the engine version manually.")

class EngineSourceLocal(EngineSource):
    def __init__(self, path : Path, config: Config):
        self.path = path
        self.config = config

    @classmethod
    def can_use(cls, project: Project, config: Config) -> bool:
        local_folder = Path(config["EngineSource.Local"]["LocalFolder"])
        local_folder /= project.engine_association

        logger.info(f"Checking for local engine source at '{local_folder}'")

        if local_folder.exists():
            matching_files = [
                f for f in local_folder.iterdir() 
                if f.is_file() and f.name.startswith(project.engine_association) and f.suffix in [".zip", ".7z" ]
            ]

            if matching_files:
                logger.info(f"Found local engine source at '{local_folder}'")
                return True
            
            logger.info(f"Found folder at '{local_folder}' but it does not contain matching engine files")
            return False
        
        logger.info(f"Did not find local engine source at '{local_folder}'")

        return False

    def copy_engine_to(self, destination: Path):    
        pass

class EngineSourceAWS(EngineSource):
    def __init__(self, path : Path, config: Config):
        self.path = path
        self.config = config

    @classmethod
    def can_use(cls, project: Project, config: Config) -> bool:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=config["EngineSource.AWS"]["AWS_AccessKey"],
            aws_secret_access_key=config["EngineSource.AWS"]["AWS_SecretKey"],
            region_name=config["EngineSource.AWS"]["AWS_Region"]
        )
    
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=config["EngineSource.AWS"]["AWS_BucketName"], Prefix=project.engine_association)
        
        files = []
        for page in pages:
            if 'Contents' in page:
                # Filter out directories (keys ending with '/')
                files.extend([obj['Key'] for obj in page['Contents'] 
                            if obj['Key'].endswith(('.zip', '.7z'))])
        
        if not files:
            return False
        
        return True
    
    def copy_engine_to(self, destination: Path):    
        pass

def resolve_engine_source(project: Project) -> EngineSource:
    config = resolve_config(project)
    if EngineSourceEGS.can_use(project, None):
        return EngineSourceEGS()
    
    sources = config["EngineSource"]["Sources"].split("+")

    for source in sources:
        source = source.strip()
        source_class = EngineSource.get_source(source)
        if source_class:
            logger.info(f"Try to use {source} as engine source")
            if source_class.can_use(project, config):
                logger.info(f"Using {source} as engine source")
                return source_class(project, config)
            
            logger.info(f"{source} cannot be used as engine source")
    
    raise Exception(f"Could not find a source for the engine '{project.engine_association}'")