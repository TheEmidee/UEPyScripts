import json
from pathlib import Path
from typing import Optional

from packaging.version import Version

from uepyscripts import logger
from uepyscripts.internal.engine_locator import EngineLocator
from uepyscripts.internal.process import PopenRunner, ProcessRunner
from uepyscripts.internal.project import Project


class Engine:
    """The engine a project uses: where it is, its version, and its Engine tools.

    Executables are never checked up front (a freshly cloned engine may not have
    built UnrealBuildTool.exe yet). A tool the OS can't start raises
    EngineToolNotStartedError when it is launched."""

    def __init__(self, project: Project, root_path: Path, runner: Optional[ProcessRunner] = None) -> None:
        self.project = project
        self.root_path = root_path
        self.path = self.root_path.joinpath("Engine").resolve()
        self.build_path = self.path.joinpath("Build").resolve()
        self.saved_path = self.path.joinpath("Saved").resolve()
        self.version = self.get_version_number()

        self._runner: ProcessRunner = runner if runner is not None else PopenRunner()
        batch_files = self.build_path / "BatchFiles"
        self._uat = batch_files / "RunUAT.bat"
        self._build_bat = batch_files / "Build.bat"
        self._ubt = self.path / "Binaries" / "DotNET" / "UnrealBuildTool" / "UnrealBuildTool.exe"
        self._editor = self.path / "Binaries" / "Win64" / "UnrealEditor.exe"

    def uat(self, args: list[str]) -> int:
        """Run UAT with exactly these arguments. Returns its exit code."""
        return self._runner.run([str(self._uat), *args])

    def ubt(self, args: list[str]) -> int:
        """Run UBT with the uproject path followed by these arguments. Returns its exit code."""
        return self._runner.run([str(self._ubt), str(self.project.uproject_path), *args])

    def compile_editor(self) -> int:
        """Build the project's editor target (Win64 Development). Returns Build.bat's exit code."""
        project = self.project
        return self._runner.run(
            [
                str(self._build_bat),
                f"{project.project_name}Editor",
                "Win64",
                "Development",
                f"-project={project.uproject_path}",
                "-WaitMutex",
                "-FromMsBuild",
                f"-log={project.root_folder}/Saved/Logs/Compile_Editor_Development_Win64.log",
            ]
        )

    def generate_project_files(self) -> int:
        """Generate the IDE project files. Goes through Build.bat, which builds UBT
        first, so it works on a freshly cloned engine. Returns Build.bat's exit code."""
        return self._runner.run([str(self._build_bat), "-projectfiles", f"-project={self.project.uproject_path}", "-game", "-rocket", "-progress"])

    def launch_editor(self) -> None:
        """Start the editor on the project in the background."""
        self._runner.start([str(self._editor), str(self.project.uproject_path)])

    def get_version_number(self) -> Version:
        version = ""

        with open(self.build_path.joinpath("Build.version")) as build_version_file:
            version_json = json.load(build_version_file)
            major = version_json["MajorVersion"]
            minor = version_json["MinorVersion"]
            patch = version_json["PatchVersion"]
            version = f"{major}.{minor}.{patch}"

        if version == "":
            raise Exception("Impossible to find the version number of the engine")

        jenkins_file = Path(self.build_path.joinpath("JenkinsBuild.version"))

        if jenkins_file.exists():
            with open(jenkins_file) as jenkins_version_file:
                version += f".{jenkins_version_file.read()}"

        return Version(version)

    def __str__(self) -> str:
        return f"""
----- Engine infos -----
* Path : {self.path}
* Version : {self.version}
----- Engine infos -----
        """


def resolve_engine(project: Project) -> Engine:
    root_path = EngineLocator().locate(project)

    engine = Engine(project, root_path)
    logger.info(engine)
    return engine
