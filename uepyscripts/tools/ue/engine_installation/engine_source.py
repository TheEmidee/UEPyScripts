from abc import ABC, abstractmethod
import os
from pathlib import Path

import boto3
import tqdm

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

    def __init__(self, project: Project, config: Config):
        self.project = project
        self.config = config
        self.source_file = None
    
    @classmethod
    def get_source(cls, name):
        return cls._registry.get(name)
    
    @abstractmethod
    def can_use(self) -> bool:
        pass

    @abstractmethod
    def copy_engine_to(self, destination: Path):
        pass

class EngineSourceEGS(EngineSource):
    def can_use(self) -> bool:
        return is_engine_from_egs(self.project.engine_association)
    
    def copy_engine_to(self, destination: Path):
        raise Exception("Engine installation via Epic Games Launcher is not supported. Please open the Epic Games Launcher and install the engine version manually.")

class EngineSourceLocal(EngineSource):
    def can_use(self) -> bool:
        local_folder = Path(self.config["EngineSource.Local"]["LocalFolder"])
        local_folder /= self.project.engine_association

        logger.info(f"Checking for local engine source at '{local_folder}'")

        if local_folder.exists():
            matching_files = [
                f for f in local_folder.iterdir() 
                if f.is_file() and f.name.startswith(self.project.engine_association) and f.suffix in [".zip", ".7z" ]
            ]

            if matching_files:
                self.source_file = Path(sorted(matching_files, key=lambda p: p.name)[-1])
                logger.info(f"Found local engine source at '{self.source_file}'")
                return True
            
            logger.info(f"Found folder at '{local_folder}' but it does not contain matching engine files")
            return False
        
        logger.info(f"Did not find local engine source at '{local_folder}'")

        return False

    def copy_engine_to(self, destination: Path):    
        total_size = os.path.getsize(self.source_file)

        destination = destination.joinpath(self.source_file.name)
    
        with open(self.source_file, 'rb') as src, open(destination, 'wb') as dst:
            # Create progress bar
            with tqdm.tqdm(total=total_size, unit='B', unit_scale=True, desc=f'Copying {os.path.basename(self.source_file)}') as pbar:
                # Copy in chunks
                chunk_size = 1024 * 1024  # 1MB chunks
                while True:
                    chunk = src.read(chunk_size)
                    if not chunk:
                        break
                    dst.write(chunk)
                    pbar.update(len(chunk))

class EngineSourceAWS(EngineSource):
    def can_use(self) -> bool:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=self.config["EngineSource.AWS"]["AWS_AccessKey"],
            aws_secret_access_key=self.config["EngineSource.AWS"]["AWS_SecretKey"],
            region_name=self.config["EngineSource.AWS"]["AWS_Region"]
        )
    
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=self.config["EngineSource.AWS"]["AWS_BucketName"], Prefix=self.project.engine_association)
        
        files = []
        for page in pages:
            if 'Contents' in page:
                # Filter out directories (keys ending with '/')
                files.extend([obj['Key'] for obj in page['Contents'] 
                            if obj['Key'].endswith(('.zip', '.7z'))])
        
        if not files:
            logger.info(f"No engine source found in AWS S3 for '{self.project.engine_association}' in the bucket '{self.config['EngineSource.AWS']['AWS_BucketName']}'")
            return False
        
        self.source_file = Path(sorted(files)[-1])
        logger.info(f"Found engine source in AWS S3: '{self.source_file}' in the bucket '{self.config['EngineSource.AWS']['AWS_BucketName']}'")
        
        return True
    
    def copy_engine_to(self, destination: Path):    
        pass

def resolve_engine_source(project: Project) -> EngineSource:
    config = resolve_config(project)
    egs = EngineSourceEGS(project, config)
    if egs.can_use():
        return egs
    
    sources = config["EngineSource"]["Sources"].split("+")

    for source_name in sources:
        source_name = source_name.strip()
        source_class = EngineSource.get_source(source_name)
        if source_class:
            logger.info(f"Try to use {source_name} as engine source")
            source = source_class(project, config)
            if source.can_use():
                logger.info(f"Using {source_name} as engine source")
                return source
            
            logger.info(f"{source_name} cannot be used as engine source")
    
    raise Exception(f"Could not find a source for the engine '{project.engine_association}'")