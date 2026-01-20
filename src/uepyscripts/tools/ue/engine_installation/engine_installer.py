from pathlib import Path
from typing import Callable, List, Optional

from .... import logger
from ....internal.config import resolve_config
from ....internal.engine import resolve_engine
from ....internal.project import Project
from ....tools.helpers import decompress_7z, is_7z_installed
from ....tools.ue.engine_installation.engine_destination import resolve_engine_destination
from ....tools.ue.engine_installation.engine_source import resolve_engine_source


class Task:
    def __init__(self, task_description: str, func : Callable[[], Optional[bool]]) -> None:
        self.task_description = task_description
        self.func = func

    def execute(self) -> Optional[bool]:
        return self.func()


class TaskList:
    def __init__(self) -> None:
        self.tasks : list[Task] = []

    def add_task(self, task: Task) -> None:
        self.tasks.append(task)

    def execute(self, unattended: bool = False) -> None:
        if not unattended:
            while True:
                prompt = (
                    "╔═══════════════════════════════════════════════════╗\n"
                    "║  Are you OK to proceed with the above operations? ║\n"
                    "╚═══════════════════════════════════════════════════╝\n"
                    "Enter Y or N: "
                )
                response = input(prompt).strip().upper()
                if response in ["Y", "N"]:
                    break
                print("Please enter Y or N")

            if response == "N":
                exit(0)

        for i, task in enumerate(self.tasks):
            logger.info(f"{i + 1}. {task.task_description}")
            try:
                result = task.execute()
                if result is False:
                    raise RuntimeError(f"task '{task.task_description}' failed")
            except Exception as e:
                logger.fatal(f"Error: {e}")
                raise e

    def print(self) -> None:
        logger.info("")
        logger.info("The following tasks will be performed:")
        for i, task in enumerate(self.tasks):
            logger.info(f"{i + 1}. {task.task_description}")
        logger.info("")


class EngineInstaller:
    def __init__(self, project: Project, unattended: bool = False) -> None:
        self.check_requirements()

        self.project = project
        try:
            self.engine_destination_folder = resolve_engine_destination(project)
        except FileNotFoundError as e:
            if unattended:
                raise e

            self.prompt_for_engine_destination()

        self.config = resolve_config(project)
        self.engine_source = resolve_engine_source(project, self.config)

    def prompt_for_engine_destination(self) -> None:
        while True:
            prompt = (
                "╔═══════════════════════════════════════════════════════════╗\n"
                "║  Where do you want to install the engine (Enter a path) ? ║\n"
                "╚═══════════════════════════════════════════════════════════╝\n"
            )
            response = input(prompt).strip()
            path = Path(response)
            if path.exists() and path.is_dir():
                self.engine_destination_folder = path
                break
            print(f"The path '{response}' does not exist or is not a folder. Please enter a valid folder path.")

    def check_requirements(self) -> None:
        if not is_7z_installed():
            raise RuntimeError("7-Zip is not installed or not found in PATH. Please install 7-Zip to proceed.")

    def get_project_platforms(self) -> List[str]:
        platforms : str = self.config["EngineUpdate.TurnKey"]["Platforms"]
        return platforms.split("+")

    def update_sdks(self, platforms: List[str]) -> None:
        engine = resolve_engine(self.project)
        for platform in platforms:
            engine.uat(["turnkey", "-command=VerifySdk", f"-platform={platform}", "-UpdateIfNeeded", "-unattended"])

    def get_task_list(self) -> TaskList:
        tasks = TaskList()

        source_full_path = self.engine_source.get_source_full_path()
        source_file_name = Path(source_full_path).name
        destination_file = self.engine_destination_folder.joinpath(source_file_name)

        if destination_file.exists():
            logger.info(
                (
                    f"The engine source file '{source_file_name}' already exists in the destination folder '{self.engine_destination_folder}'."
                    "Skipping copy."
                )
            )
        else:
            if not self.engine_destination_folder.exists():
                tasks.add_task(Task("Create engine destination folder", lambda: self.engine_destination_folder.mkdir(parents=True, exist_ok=True)))

            tasks.add_task(
                Task(
                    (
                        f"Use the source '{self.engine_source.__class__.__name__}' to copy the engine source from "
                        "'{source_full_path}' to '{self.engine_destination_folder}'"
                    ),
                    lambda: self.engine_source.copy_engine_to(self.engine_destination_folder),
                )
            )

        tasks.add_task(Task(f"Decompress the engine archive at '{destination_file}'", lambda: decompress_7z(archive_path=destination_file)))

        tasks.add_task(Task(f"Delete the engine archive at '{destination_file}'", lambda: destination_file.unlink()))

        if not self.engine_source.get_finalize_engine_operation_description(self.engine_destination_folder) == "":
            tasks.add_task(
                Task(
                    self.engine_source.get_finalize_engine_operation_description(self.engine_destination_folder),
                    lambda: self.engine_source.finalize_engine_installation(self.engine_destination_folder),
                )
            )

        project_platforms = self.get_project_platforms()

        if any(project_platforms):
            tasks.add_task(Task("Update AutoSDK with turnkey", lambda: self.update_sdks(project_platforms)))

        return tasks
