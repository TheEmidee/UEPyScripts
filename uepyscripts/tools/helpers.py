import os
from pathlib import Path
import re
import subprocess
import sys
import winreg 
import subprocess
import os
import platform

from uepyscripts import logger

def get_registry_value(
    hkey : int,
    key_path : str,
    value_name : str
    ) -> Path:
    full_path = f"{key_path}\\{value_name}"

    try:
        with winreg.OpenKey(hkey,key_path) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
            return Path(value)
    except FileNotFoundError:
        logger.debug(f"No string value in the registry for the key {full_path}")
    except Exception as e:
        logger.fatal(f"An error occurred when trying to read {full_path}: {e}")
        return None
    
def is_engine_from_egs(engine_version: str) -> bool:
    return re.search(r"^[45]\.[0-9]+(EA)?$", engine_version)

def get_env_var_value() -> str:
    key = "NODE_UE_ROOT"
    
    if key in os.environ:
        return os.environ[key]
    
    return None

def get_engine_root_folder_from_env_var(project_engine_association: str = None) -> Path:
    node_ue_root = get_env_var_value()
    
    if node_ue_root:
        path = Path(node_ue_root)
        if project_engine_association:
            path = path.joinpath(project_engine_association)
        if path.exists():
            return path
    
        raise FileNotFoundError(f"The environment variable is set to {node_ue_root} but the folder {path} does not exist")
        
    return None

def copy_with_robocopy(source : Path, destination : Path, threads=8) -> bool:
    """
    Copy a file using Robocopy with multithreading for maximum speed.
    
    Args:
        source: Path to the source file
        destination: Path to the destination directory
        threads: Number of threads to use (default: 8, max: 128)
    """
    # Check if running on Windows
    if sys.platform != 'win32':
        print("Error: Robocopy is only available on Windows.")
        return False
    
    # Check if source file exists
    if not source.is_file():
        print(f"Error: Source file '{source}' not found.")
        return False
    
    if not destination.is_dir():
        print(f"Error: Destination '{destination}' is not a directory.")
        return False
    
    # Get source directory and filename
    source_dir = os.path.dirname(source)
    filename = os.path.basename(source)
    
    # Create destination directory if it doesn't exist
    os.makedirs(destination, exist_ok=True)
    
    cmd = [
        'robocopy',
        source_dir,           # Source directory
        destination,          # Destination directory
        filename,             # File to copy
        f'/MT:{threads}',     # Multithreaded
        '/J',                 # Unbuffered I/O
        '/Z',                 # Restartable mode
        '/R:3',               # Retry 3 times on failed copies
        '/W:5',               # Wait 5 seconds between retries
        '/BYTES',             # Show sizes in bytes
        '/ETA',               # Show estimated time of arrival
    ]

    logger.info(f"Using ROBOCOPY to Copy '{filename}' from {source_dir} to {destination}...")
    
    try:
        # Run Robocopy
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Print output in real-time
        for line in process.stdout:
            print(line, end='')
        
        # Wait for process to complete
        process.wait()
        
        # Robocopy return codes:
        # 0 = No files copied (file already exists and is identical)
        # 1 = Files copied successfully
        # 2+ = Some files or directories could not be copied
        if process.returncode < 8:
            logger.info(f"\n✓ Copy completed successfully!")
            return True
        else:
            logger.error(f"\n✗ Copy completed with errors (exit code: {process.returncode})")
            logger.error(process.stderr.read())
            return False
            
    except FileNotFoundError:
        logger.error("Error: Robocopy not found. Make sure you're running on Windows.")
        return False
    except Exception as e:
        logger.error(f"Error: {e}")
        return False

def decompress_7z(archive_path : Path, output_dir : Path =None, threads : int =-1) -> bool:
    """
    Decompress a 7z archive using 7-zip with multi-threading support.
    
    Args:
        archive_path: Path to the 7z archive file
        output_dir: Directory to extract files to (default: current directory)
        threads: Number of threads to use (default: auto-detect CPU count)
    
    Returns:
        True if successful, False otherwise
    """
    
    # Determine 7z executable based on platform
    system = platform.system()
    if system == "Windows":
        seven_zip = "7z.exe"  # Assumes 7z is in PATH
    else:
        seven_zip = "7z"  # Linux/Mac
    
    # Set output directory
    if output_dir is None:
        output_dir = os.path.dirname(archive_path) or "."
    
    # Set thread count (default to CPU count)
    if threads == -1:
        threads = os.cpu_count()
    
    # Build command
    cmd = [
        seven_zip,
        "x",  # Extract with full paths
        archive_path,
        f"-o{output_dir}",  # Output directory (no space after -o)
        f"-mmt{threads}",  # Multi-threading
        "-y"  # Yes to all prompts
    ]
    
    try:
        # Run 7z process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Read and display output in real-time
        for line in process.stdout:
            line = line.strip()
            if line:
                print(line)
        
        # Wait for process to complete
        process.wait()
        
        if process.returncode == 0:
            logger.info(f"Successfully extracted: {archive_path}")
            logger.info(f"Output directory: {output_dir}")
            logger.info(f"Threads used: {threads}")
            return True
        else:
            stderr = process.stderr.read()
            logger.error(f"Error: {stderr}")
            return False
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error extracting archive: {e}")
        logger.error(f"Error output: {e.stderr}")
        return False
    except FileNotFoundError:
        logger.error(f"7-zip executable not found. Please install 7-zip and ensure it's in your PATH.")
        return False