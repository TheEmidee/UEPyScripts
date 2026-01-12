# UEPyScripts

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) 
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/) 
[![Version](https://img.shields.io/badge/version-1.1.1-green.svg)](CHANGELOG.md)

---

## Overview ✅

**UEPyScripts** is a collection of Python tools and PowerShell helpers designed to automate common Unreal Engine project tasks (builds, packaging, editor control, CI tasks, etc.). It provides a reusable CLI (`python -m uepyscripts`) and a PowerShell wrapper (`Tools/PyScript.ps1`) used across project scripts.

---

## Table of Contents 📚

- [Features](#features-)
- [Requirements](#requirements-)
- [Installation](#installation-)
- [Quick Start](#quick-start-)
- [Usage Examples](#usage-examples-)
- [Continuous Integration](#continuous-integration-)
- [Engine Installation](#engine-installation-)
- [Development & Testing](#development--testing-)
- [Contribution Guide](#contribution-guide-)
- [Support & Troubleshooting](#support--troubleshooting-)
- [License & Credits](#license--credits-)

---

## Features ✨

- Modular Python CLI for tasks (see `uepyscripts` package)
- PowerShell wrapper to call Python modules from other project scripts (`Tools/PyScript.ps1`)
- Buildgraph runner with JSON properties and config file support
- Engine utilities (check/compile/run editor, close editor)
- CI helpers (artifact rotation, S3 upload, cleanup)

---

## Requirements ⚙️

- Python 3.10 or newer
- Windows (primary target; other platforms may work)
- Unreal Engine (project-specific; config in `Config/`)

---

## Installation 🛠️

Clone into your UE project:

- You can download the sources and put them directly in your project
- Or add as a submodule:

  git submodule add git@github.com:TheEmidee/UEPyScripts Scripts/PyScripts

## Quick Start 🚀

Bootstrap the project:

- Execute the script `Bootstrap.ps1` in the folder `Tools`. This script will create:
   - `Setup.ps1` at the root of the project.
   - `Config.ini` in `Config/PyScripts`
   - `CompileAndRunEditor.ps1` also at the root
   - `BuildgraphTask.ps1` in the folder `Scripts/Project`
- Execute `Setup.ps1` to:
   1. check if python is installed, and install it if not
   2. create the python virtual environment
   3. call the script `check_engine_installation`
- Execute `CompileAndRunEditor.ps1` to compile your C++ code and run the editor when done !
- If you use buildgraph in your project:
   1. Uncomment the buildgraph properties in `Config/PyScripts/config.ini` and adapt to your project
   2. Duplicate the script `BuildgraphTask.ps1` and adapt it to run your own targets.

## Usage Examples 🔧

- Use the PowerShell wrapper `PyScripts/Tools/PyScript.ps1` to execute the python modules. This script will setup the virtual environment if needed before executing the module.

  ```powershell
  . (Join-Path -Path $PSScriptRoot -ChildPath "Scripts/PyScripts/Tools/PyScript.ps1") `
    -moduleName "uepyscripts.run.buildgraph" `
    -arguments @{
      target = "Buildgraph Task Name";
      properties = @"
      { 
          "Clean" : "True",
          "Targets" : "MyGameClient+MyGameServer",
          "TargetConfigurations" : "Development+Shipping",
      }
  "@;
    }
  ```

- You can directly call `UAT` or `UBT`:

  ```powershell
  . (Join-Path -Path $PSScriptRoot -ChildPath "Scripts/PyScripts/Tools/PyScript.ps1") `
    -moduleName "uepyscripts.run.uat" `
    -arguments @{
        arguments = @" 
        [ "turnkey" ]
  "@;
    }
  ```

- You can generate the visual studio solution:

  ```powershell
  . (Join-Path -Path $PSScriptRoot -ChildPath "Scripts/PyScripts/Tools/PyScript.ps1") -moduleName "uepyscripts.tools.generate_solution"
    }
  ```

- You can update your engine locally if it can't be found for your projectn (See below for more explanations):

  ```powershell
  .( Join-Path -Path $PSScriptRoot -ChildPath "./Scripts/PyScripts/Tools/PyScript.ps1" ) -moduleName "uepyscripts.tools.ue.check_engine_installation"
    }
  ```

## Continuous Integration ⚙️

This repository contains several modules that you can call from a continuous integration pipeline. We use Jenkins here but this should work for other tools.

All those modules are very opinionated and work with specific rules. This may lack a bit of flexibility, but this is the result of years of iterations, and it works for us.

Ideally you should be using https://github.com/TheEmidee/JenkinsFileGenerator to generate jenkinsfiles that would use the following modules.

- `uepyscripts.tools.ci.buildgraph` : This executes a buildgraph task. This module will call the internal `uepyscripts.run.buildgraph` but will inject all arguments that are required to execute a single node, using a shared storage folder to store the artifacts of the task. This basically allows to execute buildgraph tasks in parallel. 
A typical usage of this module in a jenkins pipeline script would look like:

  ```groovy
  def buildgraph_properties = """
   -set:Clean=True
   -set:Targets=MyGameClient+MyGameServer
   -set:TargetConfigurations=Development+Shipping
   """.stripIndent().trim()

   pwsh """
      ."Scripts/PyScripts/Tools/PyScript.ps1" `
         -moduleName "uepyscripts.tools.ci.buildgraph" `
         -arguments @{
               target = "${taskName}"
               build_tag = "${BUILD_TAG}"
               string_arguments = "${buildgraph_properties}"
         }
   """
  ```

  You will have to uncomment or add the entry `BuildgraphSharedStoragePath` in your `config.ini` file in `Config/PyScripts`:

  ```ini
   [Jenkins]
   ; Path to the shared storage directory
   BuildgraphSharedStoragePath = \\nas\cache\UE-BuildGraph
  ```

- `uepyscripts.tools.ci.cleanup` : This should be used when your pipeline ends, if you use `uepyscripts.tools.ci.buildgraph`. This will delete all the files that could have been created as part of the pipeline, in the shared storage folder.

  ```groovy
   stage( 'Cleanup' ) {
         pwsh """
            ."Scripts/PyScripts/Tools/PyScript.ps1" `
               -moduleName "uepyscripts.tools.ci.cleanup" `
               -arguments @{
                     build_tag = "${BUILD_TAG}"
               }
         """
   }
  ```

- `uepyscripts.tools.archives.rotate_archives` : this module allows to archive the result of packaging your game, in a shared folder. The arguments are:
   - `directory_path` : The folder where to archive the packages. Note that this module will copy the archives in a sub-folder named after the current date with the format `YYYYMMdd`. If a folder already exists with the same date, it will suffix with an incrementing counter `_XX`
   - `keep_count` : How many versions of the packages you want to keep in `directory_path`. This will remove the extraneous sub-folders to only keep `keep_count` items.
   - `folder_output_file_name` : Path to a text file where to write the path to the folder where the archive was copied. This is useful if you plan to use this folder for other tasks, such as sending a message in slack, or uploading the archives to an amazon S3 bucket

- `uepyscripts.tools.archives.upload_archives` : this module allows to upload to an amazon S3 bucket all the files inside a folder. The arguments are:
   - `local_folder` : The folder where to find the files to upload
   - `bucket_name` : The S3 bucket name
   - `region` : The region of the bucket
   - `access_key` and `secret_key` : The keys to access the bucket
   - `destination_folder` : The folder where to upload in the bucket. As with `rotate_archives`, a sub-folder with the date will be used, and if the folder exists, a suffix will be added.
   - `keep_count` : Same as with `rotate_archives`, this is used to control how many archives you want to keep.
   - `output_file` : Path to a text file where the uploaded files URLs will be stored. This can be used in your jenkinsfile to be sent to a slack channel for example.

Here's an example of how we use these 2 modules in our jenkinsfiles:

```groovy
stage( 'Rotate Archives' ) {
    pwsh """
        ."PyScripts/Tools/PyScript.ps1" `
            -moduleName "uepyscripts.tools.archives.rotate_archives" `
            -arguments @{
                directory_path = "//nas/Versions/OurGame/Development/WIP"
                keep_count = "-1"
                folder_output_file_name = "${env.WORKSPACE}/Saved/Temp/latest_archive_Development.txt"
            }
    """

    def folder_name = readFile "${env.WORKSPACE}/Saved/Temp/latest_archive_Development.txt"
    slackSend( channel: '#channel', message: "New Development build available : ${folder_name}" )
}

stage( 'Upload Archives' ) {
    def file = readFile "${env.WORKSPACE}/Saved/Temp/latest_archive_Development.txt"

    pwsh """
        ."PyScripts/Tools/PyScript.ps1" `
            -moduleName "uepyscripts.tools.archives.upload_archives" `
            -arguments @{
                local_folder = "${file}"
                bucket_name = "artifacts"
                region = "eu-west-3"
                access_key = "XXXXX"
                secret_key = "YYYYY"
                destination_folder = "Development/"
                keep_count = "-1"
                output_file = "${env.WORKSPACE}/Saved/Temp/uploaded_files_Development.txt"
            }
    """

    def uploaded_files = readFile "${env.WORKSPACE}/Saved/Temp/uploaded_files_Development.txt"
    def lines = uploaded_files.split('\n')

    if ( lines.size() > 0 ) {
        def message = 'Uploaded builds:\n'

        lines.each { String line ->
            def parts = line.split(' : ', 2)
            if (parts.size() == 2) {
                def url = parts[0].trim()
                def filename = parts[1].trim()
                message += "<${url}|${filename}>\n"
            }
        }

        slackSend( channel: '#channel', message: message )
    } else {
        slackSend( channel: '#channel', color: 'danger', message: 'No files were uploaded' )
    }
}
```

## Engine installation 🛠️

You can use the module `uepyscripts.tools.ue.check_engine_installation` to automatically install the engine version that your project requires.

The requirements for this to work are as follow:

- For now, it is not possible to install automatically engine versions from the Epic Games Launcher as it seems not possible to give arguments to EGS to do so
- You must use an installed build engine that you build from the engine sources from Perforce or Github
- The installed build engine must be zipped into a 7z archive (No sub-folders, the `Engine` folder must be at the the root of the archive)
- The archive name must match the `EngineAssociation` property of the `uproject` file. You can add additional version numbers at the end of the archive name. (For example if the `EngineAssociation` property is `UE-MyProject-5.2`, you can name your archive `UE-MyProject-5.2.7z`, or `UE-MyProject-5.2.1.297.7z` if you want to keep multiple versions of the engine)
- You must place your archives either on a shared local folder, or in an amazon S3 bucket (The engine archives must be placed in a folder named `Engine` at the root of the bucket)
- You must have installed 7-zip on your machine, and it must be accesible from the PATH

How the script works:

- It will try to resolve the project and the engine the project needs. If this succeeds, nothing has to be done, since the project can be open
- If the engine resolution fails, then an update is executed:
- Try to determine the folder where the engine must be installed by reading the environment variable `NODE_UE_ROOT`. If this environment variable exists and points to a valid folder, then this is used. Otherwise the script will prompt the user for a destination. (The environment variable is useful on build machines to allow unattended installations as part of the build pipeline)
- Choose a source for where to get the engine archives: You can configure which sources to use by updating the property `[EngineUpdate.Sources].Sources` in the `config.ini`. You can use `Local`, `AWS`, or both with `Local+AWS`. 
   - You can define where the `Local` source can fetch the archives by setting the property `[EngineUpdate.Source.Local].LocalFolder`.
   - You can define the amazon S3 properties `AWS_SecretKey`, `AWS_AccessKey`, `AWS_BucketName` and `AWS_Region` under the category `EngineUpdate.Source.AWS`. Please note that the script will look for the engine archives in the folder `Engine` of the bucket.
   - The script will try each source one at a time, and select the first source that it can reach, and that has an engine archive which has a valid name
- Create the destination folder if it does not exist, using the `EngineAssociation` property (So if the destination folder is `C:/UE` and the `EngineAssociation` is `UE-MyProject-5.2`, you will have a folder `C:/UE/UE-MyProject-5.2`)
- Copy the engine archive from the source to the destination folder
- Decompress the engine archive in-place in the destination folder (You would now have the folder `C:/UE/UE-MyProject-5.2/Engine`)
- Delete the engine archive
- Register the engine in the windows registry by creating a key named `UE-MyProject-5.2` at `HKCU\SOFTWARE\Epic Games\Unreal Engine\Builds` with the value `C:/UE/UE-MyProject-5.2/Engine`
- Update the SDKs you need to build the platforms of the project with turnkey. For this, you will have to list all the platforms in the config file by setting the property `[EngineUpdate.TurnKey]` with all the platform names, separated by `+`. Ex: `Platforms = Win64+PS5+Switch`. This will run the command `turnkey -command=VerifySdk -platform=PLATFORM -UpdateIfNeeded -unattended` for each platform.

## Development & Testing 🧪

- Setup dev environment and install dependencies:

  ```powershell
  .\setup_venv.ps1
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  ```

- Linting & formatting
  - Use `black` and `ruff` (or your chosen formatters/linters). Add checks to CI as required.

---

## Contribution Guide 🤝

We welcome contributions — please follow these steps:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-change`
4. Run lint locally
5. Submit a pull request describing the change

---

## Support & Troubleshooting ❓

- Check `Config/` and `uepyscripts/internal/config.py` for project-specific settings.
- If `buildgraph` fails, ensure `Config/Project` has a valid `BuildgraphPath` and the UAT tool is accessible.
- For PowerShell wrapper errors, verify `$PSScriptRoot` and relative paths to `Tools/PyScript.ps1` are correct.
- When reporting issues, include:
  - Python version
  - Unreal Engine version
  - Exact command and full logs

---

## License & Credits 📝

**License:** MIT — see the [LICENSE](LICENSE) file.

**Maintainers:** Michael Delva and contributors (see `AUTHORS` or repository metadata).

**Changelog:** See [CHANGELOG.md](CHANGELOG.md)

---

Made with ❤️ for Unreal Engine developers — contributions and feedback are welcome! If this helped you, consider starring the repository. ⭐

