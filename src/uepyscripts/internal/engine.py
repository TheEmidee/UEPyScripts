from pathlib import Path

from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, Field, ValidationError

from uepyscripts.internal.errors import EngineNotFoundError, InvalidEngineError, describe_json_problems
from uepyscripts.internal.process import ProcessRunner
from uepyscripts.internal.project import Project


class _BuildVersion(BaseModel):
    major: int = Field(alias="MajorVersion")
    minor: int = Field(alias="MinorVersion")
    patch: int = Field(alias="PatchVersion")


class Engine:
    """The engine a project uses: where it is, its version, and its Engine tools.

    Executables are never checked up front (a freshly cloned engine may not have
    built UnrealBuildTool.exe yet). A tool the OS can't start raises
    EngineToolNotStartedError when it is launched."""

    def __init__(self, project: Project, root_path: Path, runner: ProcessRunner) -> None:
        self.project = project
        self.root_path = root_path
        self.path = self.root_path.joinpath("Engine").resolve()
        self.build_path = self.path.joinpath("Build").resolve()
        self.saved_path = self.path.joinpath("Saved").resolve()
        self.version = self.get_version_number()

        self._runner = runner
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
        """MajorVersion.MinorVersion.PatchVersion from Build.version, followed by the
        Jenkins build number when JenkinsBuild.version exists."""
        build_version = self.build_path / "Build.version"
        try:
            numbers = _BuildVersion.model_validate_json(build_version.read_text(encoding="utf-8"))
        except FileNotFoundError as e:
            raise EngineNotFoundError(f"{self.root_path} is not an engine: {build_version} does not exist") from e
        except OSError as e:
            raise InvalidEngineError(f"Could not read {build_version}: {e}") from e
        except ValidationError as e:
            raise InvalidEngineError(f"Invalid {build_version}: {describe_json_problems(e)}") from e

        version = f"{numbers.major}.{numbers.minor}.{numbers.patch}"

        jenkins_version = self.build_path / "JenkinsBuild.version"
        if not jenkins_version.exists():
            return Version(version)

        try:
            build_number = jenkins_version.read_text(encoding="utf-8").strip()
            return Version(f"{version}.{build_number}")
        except OSError as e:
            raise InvalidEngineError(f"Could not read {jenkins_version}: {e}") from e
        except InvalidVersion as e:
            raise InvalidEngineError(f"Invalid {jenkins_version}: {build_number!r} is not a build number") from e

    def __str__(self) -> str:
        return f"""
----- Engine infos -----
* Path : {self.path}
* Version : {self.version}
----- Engine infos -----
        """
