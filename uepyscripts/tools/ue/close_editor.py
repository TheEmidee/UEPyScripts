import psutil

PROCNAME = "UnrealEditor.exe"

for proc in psutil.process_iter():
    # check whether the process name matches
    if proc.name() == PROCNAME:
        choice = input("The editor is already running. Do you want to stop it? (Y/N)")
        if choice == "Y" or choice == "y":
            proc.kill()
        break