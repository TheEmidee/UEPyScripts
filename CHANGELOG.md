# Changelog

All notable changes to this package will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

This project uses [*towncrier*](https://towncrier.readthedocs.io/) and the changes for the upcoming release can be found in <https://github.com/twisted/my-project/tree/main/changelog.d/>.

<!-- towncrier release notes start -->

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