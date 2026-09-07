"""
S3 connection info for the binary publish/sync tools.

Values are read from the project's Config/PyScripts/config.ini (section
[UGS.AWS]), and each one can be overridden by its command line argument.
Having no config file at all is fine — the command line can provide
everything — but a value that is missing from both sources is reported
before any S3 call is attempted.
"""

import argparse
from dataclasses import dataclass

from uepyscripts import logger
from uepyscripts.internal.config import Config, resolve_config
from uepyscripts.internal.project import Project

S3_CONFIG_SECTION = "UGS.AWS"

# (attribute, command line argument, config.ini key)
S3_SETTINGS_FIELDS = [
    ("bucket_name", "--s3-bucket-name", "AWS_BucketName"),
    ("bucket_region", "--s3-bucket-region", "AWS_Region"),
    ("access_key", "--s3-access-key", "AWS_AccessKey"),
    ("secret_key", "--s3-secret-key", "AWS_SecretKey"),
]


@dataclass
class S3Settings:
    bucket_name: str
    bucket_region: str
    access_key: str
    secret_key: str


def add_s3_arguments(parser: argparse.ArgumentParser) -> None:
    """Registers the S3 command line arguments, which override the config file."""
    group = parser.add_argument_group(
        "AWS S3",
        f"Defaults to the [{S3_CONFIG_SECTION}] section of Config/PyScripts/config.ini",
    )
    group.add_argument("--s3-bucket-name", type=str, help="AWS S3 Bucket Name (config: AWS_BucketName)")
    group.add_argument("--s3-bucket-region", type=str, help="AWS S3 Bucket Region (config: AWS_Region)")
    group.add_argument("--s3-access-key", type=str, help="AWS S3 Access Key (config: AWS_AccessKey)")
    group.add_argument("--s3-secret-key", type=str, help="AWS S3 Secret Key (config: AWS_SecretKey)")


def read_config_value(config: Config, key: str) -> str | None:
    """A missing config file, section or key are all treated the same way — no value."""
    if not config.valid or not config.config.has_section(S3_CONFIG_SECTION):
        return None

    value = config[S3_CONFIG_SECTION].get(key)

    return value if value else None


def resolve_s3_settings(project: Project, args: argparse.Namespace) -> S3Settings:
    """Takes the S3 info from the config file, then lets the matching command
    line arguments override each value. Exits with an explicit report of what
    is missing rather than letting the first S3 call fail."""
    config = resolve_config(project)

    values: dict[str, str] = {}
    missing: list[str] = []

    for attribute, argument, config_key in S3_SETTINGS_FIELDS:
        argument_value = getattr(args, argument.lstrip("-").replace("-", "_"), None)
        value = argument_value or read_config_value(config, config_key)

        if value:
            values[attribute] = value
        else:
            missing.append(f"  - {argument} (or [{S3_CONFIG_SECTION}] {config_key} in Config/PyScripts/config.ini)")

    if missing:
        logger.fatal("Missing S3 information:\n" + "\n".join(missing))
        exit(1)

    return S3Settings(**values)
