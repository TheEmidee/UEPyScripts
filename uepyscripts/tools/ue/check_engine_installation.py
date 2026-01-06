from ...tools.helpers import decompress_7z
from ...tools.ue.engine_installation.engine_destination import resolve_engine_destination
from ...tools.ue.engine_installation.engine_source import resolve_engine_source
from ...internal.project import resolve_project
from ...internal.engine import resolve_engine
from ... import logger

try:
    project = resolve_project()
except Exception as e:
    logger.fatal(f"Project resolution failed: {e}")
    exit(1)

try:
    engine = resolve_engine(project)
except Exception as e:
    logger.error(f"Engine resolution failed: {e}")

    try:
        engine_source = resolve_engine_source(project)
        engine_destination_folder = resolve_engine_destination(project)

        source_full_path = engine_source.get_source_full_path()
        
        engine_destination_folder.mkdir(parents=True, exist_ok=True)

        source_file_name = source_full_path.name

        if engine_destination_folder.joinpath(source_file_name).exists():
            logger.info(f"The engine source file '{source_file_name}' already exists in the destination folder '{engine_destination_folder}'. Skipping copy.")
        else:
            logger.info(f"Could not find '{source_file_name}' in '{engine_destination_folder}'. Starting engine copy...")
            engine_source.copy_engine_to(engine_destination_folder)

        destination_file = engine_destination_folder.joinpath(source_file_name)

        if not decompress_7z(
            archive_path=destination_file
            ):
            raise Exception(f"Failed to decompress the engine archive at '{destination_file}'")

        logger.info(f"Delete engine archive file.")
        destination_file.unlink()

        logger.info(f"Engine installation completed successfully.")

        # TODO
        # * Add key to registry when needed
        # * Ask confirmation to user to validate source of the copy
        # * Ask confirmation to user to validate deletion of the archive
        # * unattended mode

    except Exception as e:
        logger.fatal(f"Error when installing the engine: {e}")
        exit(1)