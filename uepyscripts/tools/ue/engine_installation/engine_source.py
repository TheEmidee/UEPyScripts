from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import quote
import winreg

from .... import logger
from ....internal.project import Project
from ....internal.config import Config, resolve_config
from ....tools.helpers import copy_with_robocopy, is_engine_from_egs
from ....tools.s3.s3_client import S3Client
from ....tools.winreg import write_registry_value

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
    def copy_engine_to(self, destination_folder: Path):
        pass

    def get_source_full_path(self) -> Path:
        return self.source_file
    
    @abstractmethod
    def finalize_engine_installation(self, destination_folder: Path):
        pass

class EngineSourceEGS(EngineSource):
    def can_use(self) -> bool:
        return is_engine_from_egs(self.project.engine_association)
    
    def copy_engine_to(self, destination_folder: Path):
        raise Exception("Engine installation via Epic Games Launcher is not supported. Please open the Epic Games Launcher and install the engine version manually.")
    
    def finalize_engine_installation(self, destination_folder: Path):
        pass

class EngineSourceInstalledBuild(EngineSource):
    def finalize_engine_installation(self, destination_folder):
        write_registry_value(winreg.HKEY_CURRENT_USER,r"SOFTWARE\Epic Games\Unreal Engine\Builds",self.project.engine_association,str(destination_folder))

class EngineSourceLocal(EngineSourceInstalledBuild):
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

    def copy_engine_to(self, destination_folder: Path):
        copy_with_robocopy(self.source_file, destination_folder)

class EngineSourceAWS(EngineSourceInstalledBuild):
    def __init__(self, project, config):
        super().__init__(project, config)
        self.s3_client = S3Client(
            access_key=self.config["EngineSource.AWS"]["AWS_AccessKey"],
            secret_key=self.config["EngineSource.AWS"]["AWS_SecretKey"],
            region=self.config["EngineSource.AWS"]["AWS_Region"]
        )
        
    def can_use(self) -> bool:
        files = self.s3_client.get_bucket_files(
            bucket_name=self._get_bucket_name(),
            prefix=self.project.engine_association,
            filter_func=lambda obj: obj['Key'].endswith(('.zip', '.7z'))
        )
        
        if not files:
            logger.info(f"No engine source found in AWS S3 for '{self.project.engine_association}' in the bucket '{self.config['EngineSource.AWS']['AWS_BucketName']}'")
            return False
        
        self.source_file = Path(sorted(files)[-1])
        logger.info(f"Found engine source in AWS S3: '{self.source_file}' in the bucket '{self.config['EngineSource.AWS']['AWS_BucketName']}'")
        
        return True
    
    def copy_engine_to(self, destination_folder: Path):    
        self.s3_client.download_file(
            bucket_name=self._get_bucket_name(),
            key=str(self.source_file),
            local_folder=destination_folder,
            show_progress_bar=True
        )

    def _get_bucket_name(self) -> str:
        return self.config["EngineSource.AWS"]["AWS_BucketName"]

    def get_source_full_path(self) -> Path:
        base_url = f"https://{self._get_bucket_name()}.s3.amazonaws.com"
    
        # URL encode the key to handle special characters
        encoded_key = quote(str(self.source_file), safe='/')
        return Path(f"{base_url}/{encoded_key}")

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