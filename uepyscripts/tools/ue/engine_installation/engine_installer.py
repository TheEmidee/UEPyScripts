from pathlib import Path
from .... import logger
from ....internal.project import Project
from ....tools.helpers import decompress_7z
from ....tools.ue.engine_installation.engine_destination import resolve_engine_destination
from ....tools.ue.engine_installation.engine_source import resolve_engine_source


class Task:
    def __init__(self, task_description: str, func):
        self.task_description = task_description
        self.func = func
    
    def execute(self):
        self.func()

class TaskList:
    def __init__(self):
        self.tasks = []
    
    def add_task(self, task: Task):
        self.tasks.append(task)
    
    def execute(self):
        for i, task in enumerate(self.tasks):
            logger.info(f"{i+1}. {task.task_description}")
            try:
                result = task.execute()
                if result is False:
                    raise RuntimeError(f"task '{task.task_description}' failed")
            except Exception as e:
                logger.fatal(f"Error: {e}")
                raise e

    def print(self):
        logger.info("")
        logger.info("The following tasks will be performed:")
        for i, task in enumerate(self.tasks):
            logger.info(f"{i+1}. {task.task_description}")
        logger.info("")

class EngineInstaller:
    def __init__(self, project : Project):
        self.project = project
        self.engine_source = resolve_engine_source(project)
        self.engine_destination_folder = resolve_engine_destination(project)

    def get_task_list(self) -> TaskList:
        tasks = TaskList()
        
        source_full_path = self.engine_source.get_source_full_path()
        source_file_name = Path(source_full_path).name
        destination_file = self.engine_destination_folder.joinpath(source_file_name)

        if destination_file.exists():
            logger.info(f"The engine source file '{source_file_name}' already exists in the destination folder '{self.engine_destination_folder}'. Skipping copy.")
        else:
            # logger.info(f"Could not find '{source_file_name}' in '{self.engine_destination_folder}'. Starting engine copy...")
            if not self.engine_destination_folder.exists():
                tasks.add_task(
                    Task(
                        "Create engine destination folder",
                        lambda: self.engine_destination_folder.mkdir(parents=True, exist_ok=True)
                    )
                )

            tasks.add_task(
                Task(
                    f"Use the source '{self.engine_source.__class__.__name__}' to copy the engine source from '{source_full_path}' to '{self.engine_destination_folder}'",
                    lambda: self.engine_source.copy_engine_to(self.engine_destination_folder)
                )
            )

        tasks.add_task(
            Task(
                f"Decompress the engine archive at '{destination_file}'",
                lambda: decompress_7z( archive_path=destination_file )
            )
        )

        tasks.add_task(
            Task(
                f"Delete the engine archive at '{destination_file}'",
                lambda: destination_file.unlink()
            )
        )

        if not self.engine_source.get_finalize_engine_operation_description(self.engine_destination_folder) == "":
            tasks.add_task(
                Task(
                    self.engine_source.get_finalize_engine_operation_description(self.engine_destination_folder),
                    lambda: self.engine_source.finalize_engine_installation(self.engine_destination_folder)
                )
            )

        return tasks