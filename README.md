# UEPyScripts

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) 
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/) 
[![Version](https://img.shields.io/badge/version-1.1.1-green.svg)](CHANGELOG.md)

---

## Overview ✅

**UEPyScripts** is a collection of Python tools and PowerShell helpers designed to automate common Unreal Engine project tasks (builds, packaging, editor control, CI tasks, etc.). 

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

- Multiple helper scripts:
  - Engine Utilities
    - ue-run-buildgraph
    - ue-close-editor
    - ue-compile-editor
    - ue-run-editor
    - ue-check-engine-installation
  - Continuous Integration helpers:
    - ue-ci-cleanup
    - ue-ci-run-buildgraph

---

## Requirements ⚙️

- Python 3.10 or newer
- Windows (primary target; other platforms may work)
- Unreal Engine (project-specific; config in `Config/`)

---

## Installation 🛠️

- The easy way is to use [UEPyScriptsBootstrap](https://github.com/TheEmidee/UEPyScriptsBootstrap)
- You can download the sources and put them directly in your project
- You can add as a submodule: `git submodule add git@github.com:TheEmidee/UEPyScripts Scripts/PyScripts`
- You can add as a python requirement:

  - Create a file named `requirements.txt`
  - Add `UEPyScripts>=1.2.1` in this file
  - Activate a virtual environment : `python -m venv .venv` and `& ".\.venv\Scripts\Activate.ps1"`
  - Upgrade pip : `python -m pip install --upgrade pip`
  - Install the module : `pip install -r requirements --upgrade`

## Usage Examples 🔧

- Execute a buildgraph target

  ```bash
  ue-run-buildgraph.exe --target "Buildgraph Task Name" -set:Clean=True -set:Targets=MyGameClient+MyGameServer -set:TargetConfigurations=Development+Shipping
  ```

- You can directly call `UAT` or `UBT`:

  ```bash
    ue-run-uat.exe turnkey
  ```

- You can generate the visual studio solution:

  ```bash
    ue-generate-solution.exe
  ```

- You can update your engine locally if it can't be found for your projectn (See below for more explanations):

  ```bash
  ue-check-engine-installation.exe
  ```

## Continuous Integration ⚙️

This repository contains several modules that you can call from a continuous integration pipeline. We use Jenkins here but this should work for other tools.

All those modules are very opinionated and work with specific rules. This may lack a bit of flexibility, but this is the result of years of iterations, and it works for us.

Ideally you should be using https://github.com/TheEmidee/JenkinsFileGenerator to generate jenkinsfiles that would use the following modules.

- `uepyscripts.tools.ci.buildgraph` : This executes a buildgraph task. This module will call the internal `uepyscripts.run.buildgraph` but will inject all arguments that are required to execute a single node, using a shared storage folder to store the artifacts of the task. This basically allows to execute buildgraph tasks in parallel. 
A typical usage of this module in a jenkins pipeline script would look like:

  ```groovy
  pwsh """
      ."Scripts/Python/.venv/Scripts/ue-ci-run-buildgraph.exe" `
        --target="${taskName}" `
        --build_tag = "${BUILD_TAG}"
        -set:Clean=True
        -set:Targets=MyGameClient+MyGameServer
        -set:TargetConfigurations=Development+Shipping
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
      ."Scripts/Python/.venv/Scripts/ue-ci-cleanup.exe" --build_tag="${BUILD_TAG}"
      """
   }
  ```

## Engine installation 🛠️

You can use the module `uepyscripts.tools.ue.check_engine_installation` (or `ue-check-engine-installation`) to automatically install the engine version that your project requires.

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
  ```

- Linting & formatting
  - Use `ruff check .` and `ruff format .` Add checks to CI as required.
  - Use `mypy .`

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

