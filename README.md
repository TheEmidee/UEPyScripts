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
- [Configuration](#configuration-)
- [Continuous Integration](#continuous-integration-)
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
  - Continuous Integration helpers:
    - ue-ci-cleanup
    - ue-ci-run-buildgraph

---

## Requirements ⚙️

- Python 3.12 or newer
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

## Configuration 🗂️

Commands read the **Project config**: every `.ini` file in your project's `Config/PyScripts` folder. The files are merged in file-name order, so a later file overrides the same key in an earlier one (for example `config.ini`, then `config.local.ini`). Not having the folder is fine: a command only fails when it needs a key that isn't set, and the error lists every missing or malformed key of that section.

- Keys are case-insensitive. `Key =` with nothing after it counts as not set.
- Lists use `+` as the separator.
- Relative paths are resolved against the folder that holds the `.uproject` file.
- Sections and keys not listed here are ignored.

```ini
[Project]
; BuildGraph XML used by ue-run-buildgraph when --script isn't passed
BuildgraphPath = Build/BuildGraph.xml
; Extra automation script folders passed to UAT as -ScriptDir (missing folders are skipped with a warning)
AutomationScriptsDirectories = Build/Scripts+Plugins/MyPlugin/Build/Scripts
; Properties passed to BuildGraph as -set:Name=Value (split on the first =)
BuildgraphSharedProperties = Clean=False+Targets=MyGameEditor

[Jenkins]
; Shared storage used by ue-ci-run-buildgraph and ue-ci-cleanup (required by both)
BuildgraphSharedStoragePath = \\nas\cache\UE-BuildGraph

[UGS.AWS]
; Used by ue-ugs-push, ue-ugs-pull and ue-ugs-cleanup.
; Each value can be overridden on the command line (--s3-bucket-name, --s3-bucket-region, --s3-access-key, --s3-secret-key)
AWS_BucketName = my-bucket
AWS_Region = eu-west-1
AWS_AccessKey = ...
AWS_SecretKey = ...
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

## Development & Testing 🧪

- Install [Astral UV](https://docs.astral.sh/uv/)
- Setup dev environment and install dependencies:

  ```powershell
  .\setup-venv.ps1
  ```

- In VS Code, you can create a `launch.json` file like this one. It's important to use the `module` setting so that relative imports don't raise exceptions.

```
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python Debugger: Current File",
            "type": "debugpy",
            "request": "launch",
            "module": "uepyscripts.tools.ue.compile_editor",
            "cwd": "ABSOLUTE_PATH_TO_PROJECT",
            "console": "integratedTerminal",
            "args": [
                "--uproject-path=D:\\PATH_TO_UPROJECT.uproject"
            ]
        }
    ]
}
```

- Linting & formatting
  - Use `uv run ruff check .` and `uv run ruff format .` Add checks to CI as required.
  - Use `uv run mypy .`

To create a new release, you must be on the `develop` branch, and call `invoke create_release`

---

## Contribution Guide 🤝

We welcome contributions — please follow these steps:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-change`
3. Add entries in the .changelog folder for towncrier. You can read the [README](.changelog/README.md) file for more information.
4. Run lint locally
5. Update documentation
6. Submit a pull request describing the change


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

