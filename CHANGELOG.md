# Changelog

All notable changes to this package will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

This project uses [*towncrier*](https://towncrier.readthedocs.io/) and the changes for the upcoming release can be found in <https://github.com/twisted/my-project/tree/main/changelog.d/>.

<!-- towncrier release notes start -->

## [1.5.0] - 2026-11-10

### Removed

- UGS.cleanup now owns retention. It keeps the newest `--keep-versions` published commits per remote branch and deletes unreferenced blobs older than `--blob-grace-hours`. UGS.push doesn't prune anymore and no longer accepts `--checkpoint_interval`, `--keep_checkpoints` or `--checkpoint-branch`. ([#30](https://github.com/TheEmidee/JenkinsFileGenerator/issues/30))
- Removed the `ue-check-engine-installation` command and its automatic engine installation, including copying engine archives from a local folder or S3, registering the engine, and updating platform SDKs with Turnkey. ([#31](https://github.com/TheEmidee/JenkinsFileGenerator/issues/31))
- Removed the `uepyscripts.context` module. Scripts that imported `project`, `engine` or `config` from it should use `uepyscripts.internal.workspace.Workspace` instead. ([#32](https://github.com/TheEmidee/JenkinsFileGenerator/issues/32))
- Removed the `--keep-temp-directory` argument of `ue-ugs-push`. The temporary file it kept is now always cleaned up, so jobs that pass it should drop it. ([#42](https://github.com/TheEmidee/JenkinsFileGenerator/issues/42))

### Changed

- UGS now uses a content-addressed bucket. Push stores each file once, as a zstd-compressed blob named after its hash, and writes one manifest per published commit. Pull downloads only the files that differ from the last sync, so switching branches fetches what changed. UGS no longer needs deltas, checkpoints or 7-Zip. Empty existing buckets before the first push with this version. ([#30](https://github.com/TheEmidee/JenkinsFileGenerator/issues/30))
- All commands that work on a project now accept `--uproject-path` to point at the `.uproject` file instead of searching up from the current folder. `ue-run-buildgraph` renamed its `--uproject` argument to `--uproject-path`, and `ue-run-uat` and `ue-run-ubt` forward every other argument to UAT and UBT unchanged. ([#32](https://github.com/TheEmidee/JenkinsFileGenerator/issues/32))
- The `.ini` files in `Config/PyScripts` are now merged in file-name order, so a later file reliably overrides an earlier one. ([#36](https://github.com/TheEmidee/JenkinsFileGenerator/issues/36))
- `ue-generate-solution` now goes through `Build.bat`, which builds UnrealBuildTool first, so it works on a freshly cloned engine. ([#38](https://github.com/TheEmidee/JenkinsFileGenerator/issues/38))
- `ue-run-buildgraph` now requires `--target`, since Single nodes are only run by `ue-ci-run-buildgraph`, and no longer requires `--uproject-path` with `--script`. Extra arguments passed to either BuildGraph command now replace a generated argument with the same key (for example `-Project=` or `-NoP4`) instead of adding a duplicate, and each `-set:` property is passed once, with the command line overriding `BuildgraphSharedProperties`. `ue-ci-run-buildgraph` also accepts `--script`. ([#40](https://github.com/TheEmidee/JenkinsFileGenerator/issues/40))
- `ue-ugs-push`, `ue-ugs-pull` and `ue-ugs-cleanup` now report missing S3 settings and non-native projects the same way as every other command, with all missing `[UGS.AWS]` keys and their `--s3-*` arguments listed together. `--jobs` has the same help text in all three. ([#44](https://github.com/TheEmidee/JenkinsFileGenerator/issues/44))
- `ue-ci-run-buildgraph` and `ue-ci-cleanup` now fail when a Shared storage folder cannot be removed, instead of leaving it on the share silently. A missing `--build_tag` (or `--target`) is reported as a usage error. ([#45](https://github.com/TheEmidee/JenkinsFileGenerator/issues/45))

### Fixed

- UGS.cleanup reads its S3 settings from config.ini, like push and pull. UGS.pull saves .sync-state.json at the engine root instead of the current directory. Two concurrent pushes can't lose a published commit anymore. ([#30](https://github.com/TheEmidee/JenkinsFileGenerator/issues/30))
- Commands now look for the engine only when they need it, so `ue-ci-cleanup` runs on machines without an engine installed, and `ue-ci-run-buildgraph` no longer finds the project twice. ([#32](https://github.com/TheEmidee/JenkinsFileGenerator/issues/32))
- Commands no longer crash when the project has no `Config/PyScripts` folder or when a `BuildgraphSharedProperties` value contains `=`. A missing or malformed config value now stops the command with one error that lists every problem in that section. ([#36](https://github.com/TheEmidee/JenkinsFileGenerator/issues/36))
- An engine tool that hasn't been built yet (for example `UnrealBuildTool.exe` or `RunUAT.bat` missing) now stops the command with a clear error, instead of an `AttributeError` about a `Runner` object. ([#38](https://github.com/TheEmidee/JenkinsFileGenerator/issues/38))
- `ue-run-uat` and `ue-run-ubt` now forward `-help`, `-h`, `--help` and any other argument starting with `-h` to UAT and UBT, instead of printing their own help. ([#39](https://github.com/TheEmidee/JenkinsFileGenerator/issues/39))
- A missing or non-XML BuildGraph script now stops `ue-run-buildgraph` and `ue-ci-run-buildgraph` with a clear error instead of a traceback. ([#40](https://github.com/TheEmidee/JenkinsFileGenerator/issues/40))
- `ue-ugs-push` now reports the output of `symstore.exe` when indexing fails, and stops before uploading anything when the symbol store is enabled without `--symbol-store-path`. Hash caches no longer keep entries for files that were deleted. ([#42](https://github.com/TheEmidee/JenkinsFileGenerator/issues/42))
- `ue-ugs-pull` no longer crashes on an unreadable `.sync-state.json`: it logs a warning and downloads every file of the target version. ([#43](https://github.com/TheEmidee/JenkinsFileGenerator/issues/43))


## [1.4.5] - 2026-11-10

### Fixed

- Added folder "Engine/Platforms" to folders tracked by UGS.push ([#28](https://github.com/TheEmidee/JenkinsFileGenerator/issues/28))


## [1.4.4] - 2026-09-07

### Changed

- Unified settings between UGS push and pull: they are first fetched from the config.ini of the uproject, and can be override by console arguments ([#27](https://github.com/TheEmidee/JenkinsFileGenerator/issues/27))


## [1.4.3] - 2026-09-04

### Fixed

- Fixed git_utils.get_local_ancestry to support shallow clones ([#26](https://github.com/TheEmidee/JenkinsFileGenerator/issues/26))


## [1.4.2] - 2026-09-04

### Changed

- Removed local hash cache in ugs.push in favor of storing it per commit SHA in the bucket ([#25](https://github.com/TheEmidee/JenkinsFileGenerator/issues/25))


## [1.4.1] - 2026-09-03

### Changed

- Moved py.typed to the correct location

## [1.4.0] - 2026-09-03

### Added

- Added UGS scripts
  Added argument no-single-node to tools.ci.buildgraph ([#24](https://github.com/TheEmidee/JenkinsFileGenerator/issues/24))

### Changed

- Allowed run.buildgraph to run on external uproject and xml scripts ([#24](https://github.com/TheEmidee/JenkinsFileGenerator/issues/24))


## [1.3.0] - 2026-07-24

### Changed

- Added support for native projects when resolving the project or the engine ([#23](https://github.com/TheEmidee/JenkinsFileGenerator/issues/23))


## [1.2.7] - 2026-07-03

### Fixed

- Fixed the engine resolver by path which would return a semantically valid path to a non-existing directory, preventing the resolution of the engine path with the remaining methods ([#22](https://github.com/TheEmidee/JenkinsFileGenerator/issues/22))


## [1.2.6] - 2026-06-25

### Fixed

- Various fixes for the engine resolver ([#21](https://github.com/TheEmidee/JenkinsFileGenerator/issues/21))


## [1.2.5] - 2026-06-23

### Changed

- - Added optional path to a uproject file in `resolve_project` ([#20](https://github.com/TheEmidee/JenkinsFileGenerator/issues/20))


## [1.2.4] - 2026-03-19

### Fixed

- Don't throw an exception when there's no property Project:BuildgraphSharedProperties in the config.ini file ([#19](https://github.com/TheEmidee/JenkinsFileGenerator/issues/19))


## [1.2.3] - 2026-02-10

### Changed

- Made the scripts in the tools folder return an error code when something goes wrong
  Updated toolchain to use UV
  Updated GitHub actions to use UV ([#16](https://github.com/TheEmidee/JenkinsFileGenerator/issues/16))


## [1.2.2] - 2026-01-28

No significant changes.


## [1.2.1] - 2026-01-28

### Added

- Try to find the engine installation path from LauncherInstalled.dat of the EGS program data when the information can't be found in the registry ([#14](https://github.com/TheEmidee/JenkinsFileGenerator/issues/14))


## [1.2.0] - 2026-01-26

### Removed

- Removed archive scripts to move them in PyGameDevTools ([#13](https://github.com/TheEmidee/JenkinsFileGenerator/issues/13))

### Added

- Added pyproject.toml
  Added invoke commands `create_release` and `check_release`
  Added script shortcuts for scripts used by the project ([#12](https://github.com/TheEmidee/JenkinsFileGenerator/issues/12))
- Added requirement to GameDevTools ([#13](https://github.com/TheEmidee/JenkinsFileGenerator/issues/13))

### Changed

- Changed how buildgraph take arguments : no need to pass JSON strings containing arrays of arguments, or dictionaries of properties. We can now directly execute buildgraph like so : `.venv\Scripts\ue-run-buildgraph.exe" "BuildGraphTarget" -set:Property=Value -set:Property2=Value -BuildMachine -NoP4` This is valid for both CI and regular buildgraph.
  Updated github actions to ease releasing the package ([#12](https://github.com/TheEmidee/JenkinsFileGenerator/issues/12))

### Fixed

- Fixed Tools/BootStrap.ps1 to create the Scripts/Project before creating the buildgraph test script
  Fixed Tools/BootStrap.ps1 to use the script shorcuts defined in pyproject.toml
  Fixed setup_venv.ps1 to call Push-Location with the script location
  Fixed invalid raised exception in check_engine_installation when does not need to do anything
  Fixed waiting for the unreal editor process to end when running it ([#12](https://github.com/TheEmidee/JenkinsFileGenerator/issues/12))


## [1.1.1] - 2026-01-12

### Fixed

- `uepyscripts.run.buildgraph` won't fail is no properties are passed
- `uepyscripts.run.buildgraph` will surround properties that contain spaces with double quotes

## [1.1.0] - 2026-01-12

### Added

- The engine installer can now update the platformn SDKs with turnkey

## [1.0.0] - 2026-01-08

### Added

- First version of the package.