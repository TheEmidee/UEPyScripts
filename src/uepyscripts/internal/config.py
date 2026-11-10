"""
The Project config: the .ini files in the project's Config/PyScripts folder,
merged in file-name order (a later file overrides an earlier one). A missing
folder is an empty Project config.

Each Config section is read as one typed value, the first time a command asks
for it, so a command never fails because of a section it doesn't use. Missing
required keys and malformed values are all reported together in one
ConfigError. Keys the code doesn't know are ignored, and `Key =` with nothing
after it counts as missing.
"""

import configparser
from pathlib import Path
from typing import Any, ClassVar, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator
from pydantic_core import ErrorDetails

from uepyscripts import logger
from uepyscripts.internal.errors import WorkspaceError
from uepyscripts.internal.project import Project


class ConfigError(WorkspaceError):
    """A Config section has missing required keys or malformed values."""

    def __init__(self, section: str, problems: list[str], folder: Path) -> None:
        self.section = section
        self.problems = problems
        self.folder = folder
        details = "\n".join(f"  - {problem}" for problem in problems)
        super().__init__(f"Invalid [{section}] section in the Project config at {folder}:\n{details}")


def _split_list(value: str) -> list[str]:
    return [item.strip() for item in value.split("+") if item.strip()]


def _project_path(value: str, info: ValidationInfo) -> Path:
    """An absolute path, with relative ones resolved against the project root."""
    path = Path(value)
    if path.is_absolute():
        return path

    assert info.context is not None
    project_root: Path = info.context["project_root"]
    return (project_root / path).resolve()


class ConfigSection(BaseModel):
    """One [Section] of the Project config. Field aliases are the ini keys."""

    model_config = ConfigDict(frozen=True)

    section_name: ClassVar[str]


class ProjectSection(ConfigSection):
    section_name: ClassVar[str] = "Project"

    buildgraph_path: Optional[Path] = Field(default=None, alias="BuildgraphPath")
    automation_scripts_directories: list[Path] = Field(default_factory=list, alias="AutomationScriptsDirectories")
    buildgraph_shared_properties: dict[str, str] = Field(default_factory=dict, alias="BuildgraphSharedProperties")

    @field_validator("buildgraph_path", mode="before")
    @classmethod
    def _parse_buildgraph_path(cls, value: str, info: ValidationInfo) -> Path:
        return _project_path(value, info)

    @field_validator("automation_scripts_directories", mode="before")
    @classmethod
    def _parse_directories(cls, value: str, info: ValidationInfo) -> list[Path]:
        return [_project_path(item, info) for item in _split_list(value)]

    @field_validator("buildgraph_shared_properties", mode="before")
    @classmethod
    def _parse_properties(cls, value: str) -> dict[str, str]:
        properties: dict[str, str] = {}
        malformed: list[str] = []
        for pair in _split_list(value):
            name, separator, property_value = pair.partition("=")
            if not separator or not name.strip():
                malformed.append(f"'{pair}'")
                continue
            properties[name.strip()] = property_value.strip()

        if malformed:
            raise ValueError(f"not Name=Value pairs: {', '.join(malformed)}")
        return properties


class JenkinsSection(ConfigSection):
    section_name: ClassVar[str] = "Jenkins"

    buildgraph_shared_storage_path: Path = Field(alias="BuildgraphSharedStoragePath")


class UgsAwsSection(ConfigSection):
    """Every key is optional: each one can also come from the command line (see ugs.s3_settings)."""

    section_name: ClassVar[str] = "UGS.AWS"

    bucket_name: Optional[str] = Field(default=None, alias="AWS_BucketName")
    bucket_region: Optional[str] = Field(default=None, alias="AWS_Region")
    access_key: Optional[str] = Field(default=None, alias="AWS_AccessKey")
    secret_key: Optional[str] = Field(default=None, alias="AWS_SecretKey")


SectionT = TypeVar("SectionT", bound=ConfigSection)


class Config:
    def __init__(self, folder: Path, project_root: Path) -> None:
        self.folder = folder
        self._project_root = project_root
        self._parser = configparser.ConfigParser()
        self._sections: dict[type[ConfigSection], ConfigSection] = {}

        ini_files = sorted(folder.glob("*.ini"), key=lambda path: path.name.lower()) if folder.is_dir() else []
        for ini_file in ini_files:
            logger.debug(f"Reading file: {ini_file}")
        self._parser.read(ini_files)

    @property
    def project(self) -> ProjectSection:
        return self._section(ProjectSection)

    @property
    def jenkins(self) -> JenkinsSection:
        return self._section(JenkinsSection)

    @property
    def ugs_aws(self) -> UgsAwsSection:
        return self._section(UgsAwsSection)

    def _section(self, section_type: type[SectionT]) -> SectionT:
        """Read on first access, then cached. The ini files are only read once, when the Config is built."""
        cached = self._sections.get(section_type)
        if cached is not None:
            return cached  # type: ignore[return-value]

        section = section_type.section_name
        raw: dict[str, Any] = {}
        if self._parser.has_section(section):
            for field in section_type.model_fields.values():
                key = field.alias
                assert key is not None
                value = self._parser.get(section, key, fallback="").strip()
                if value:
                    raw[key] = value

        try:
            parsed = section_type.model_validate(raw, context={"project_root": self._project_root})
        except ValidationError as e:
            raise ConfigError(section, [_describe(error) for error in e.errors()], self.folder) from e

        self._sections[section_type] = parsed
        return parsed


def _describe(error: ErrorDetails) -> str:
    key = ".".join(str(part) for part in error["loc"])
    if error["type"] == "missing":
        return f"{key}: missing"

    message = str(error["msg"]).removeprefix("Value error, ")
    return f"{key}: {message} (value: {error['input']!r})"


def resolve_config(project: Project) -> Config:
    return Config(project.project_folders.config.joinpath("PyScripts"), project.root_folder)
