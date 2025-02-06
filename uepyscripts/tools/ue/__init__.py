import psutil
from uepyscripts import engine
from uepyscripts import project

def compile_editor():
    engine.build([
        f"{project.project_name}Editor",
        "Win64",
        "Development",
        f"-project={project.uproject_path}",
        "-WaitMutex",
        "-FromMsBuild",
        f"-log={project.root_folder}/Saved/Logs/Compile_Editor_Development_Win64.log"
    ])

def close_editor():
    PROCNAME = "UnrealEditor.exe"

    for proc in psutil.process_iter():
        # check whether the process name matches
        if proc.name() == PROCNAME:
            choice = input("The editor is already running. Do you want to stop it? (Y/N)")
            if choice == "Y" or choice == "y":
                proc.kill()
            break

def run_editor(wait : bool = False):
    args : list[str] = None
    if wait:
        args = [ "-wait" ]
    
    engine.run_editor(args)