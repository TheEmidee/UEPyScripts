from uepyscripts import logger
from uepyscripts.internal.project import Project
from pathlib import Path
from packaging.version import Version
from uepyscripts.internal.engine_resolver import resolve_engine_path

import json
import io
import subprocess

class Engine:
    class Runner:
        def __init__(
                self, 
                path : Path,
                extra_args : list[str] = []
                ):
            if not path.exists():
                raise FileNotFoundError(f"The file {path} does not exist")
            
            self.path = path.resolve()
            self.extra_args = extra_args

        def run(
                self, 
                args : list[str] = []
                ):
            logger.debug(f"run process for {self.path} with arguments {args}")
    
            try:
                process  = subprocess.Popen(
                    [str(self.path)] + self.extra_args + args,
                    stdout=subprocess.PIPE
                )

                for line in io.TextIOWrapper(process.stdout, encoding="utf-8"):
                    logger.info(line.replace('\n',''))
                
                return process.returncode

            except subprocess.CalledProcessError as e:
                logger.fatal(f"Error occured when running {self.path}. ")
                logger.fatal(f"Error occurred: {e}")
                logger.fatal(f"Error code: {e.returncode}")
                logger.fatal(f"Stderr: {e.stderr}")
    
    def __init__(self, project : Project):
        self.project = project
        self.root_path = resolve_engine_path(project)
        self.path = self.root_path.joinpath("Engine").resolve()
        self.version = self.get_version_number()
        self.uat_path = self.Runner(self.path.joinpath("Build/BatchFiles/RunUAT.bat"))
        self.ubt_path = self.Runner(self.path.joinpath("Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.exe"),{self.project.uproject_path})
        self.build_bat_path = self.Runner(self.path.joinpath("Build/BatchFiles/Build.bat"))
        self.editor_exe_path = self.Runner(self.path.joinpath("Binaries/Win64/UnrealEditor.exe"),{self.project.uproject_path})

    def uat(self, args: list[str] = None):
        self.uat_path.run(args)

    def ubt(self, args: list[str] = None):
        self.ubt_path.run(args)

    def build(self, args: list[str] = None):
        self.build_bat_path.run(args)

    def run_editor(self, args: list[str] = None):
        self.editor_exe_path.run(args)

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
    
    def get_short_version_number(self) -> str:
        return f"{self.version.major}.{self.version.minor}"

    def __str__(self):
        return f"""
----- Engine infos -----
* Path : {self.path}
* Version : {self.version}
----- Engine infos -----
        """

def resolve_engine(project: Project) -> Engine:
    engine = Engine(project)
    logger.info(engine)
    return engine