from abc import ABC
from typing import Any, Dict, Optional
from pydantic import BaseModel, field_validator

from uepyscripts.ci.jenkins.core.base_feature import BaseFeature, FeatureConfig

class SlackNotificationMessageConfig(BaseModel,ABC):
    enabled: bool = False
    color : str = None
    channel_override : str = ""

class SlackNotificationSimpleMessageConfig(SlackNotificationMessageConfig):
    enabled: bool = True
    message: str = ""

class SlackNotificationBlocksMessageConfig(SlackNotificationMessageConfig):
    enabled: bool = False
    blocks: str = ""

class SlackNotificationEventConfig(BaseModel,ABC):
    simple_message: SlackNotificationSimpleMessageConfig = SlackNotificationSimpleMessageConfig()
    blocks_message: SlackNotificationBlocksMessageConfig = SlackNotificationBlocksMessageConfig()

    def _merge_with_defaults(self, field_name: str, default_factory):
        current = getattr(self, field_name)
        if current is None:
            setattr(self, field_name, default_factory())
        else:
            default = default_factory()
            # Fill in missing fields from default
            for k, v in default.model_dump().items():
                if getattr(current, k, None) in (None, "", False):
                    setattr(current, k, v)

    def model_post_init(self, __context: Any) -> None:
        # Each subclass can call this with its own logic
        pass

class SlackNotificationPreBuildStepEventConfig(SlackNotificationEventConfig):
    def model_post_init(self, __context: Any) -> None:
        self._merge_with_defaults(
            "simple_message",
            lambda: SlackNotificationSimpleMessageConfig(
                enabled=True,
                message="Build Started",
                color="#0000FF"
            )
        )
        self._merge_with_defaults(
            "blocks_message",
            lambda: SlackNotificationBlocksMessageConfig(
                enabled=False,
                blocks="[]",
                color="#0000FF"
            )
        )

class SlackNotificationOnSuccessEventConfig(SlackNotificationEventConfig):
    def model_post_init(self, __context: Any) -> None:
        self._merge_with_defaults(
            "simple_message",
            lambda: SlackNotificationSimpleMessageConfig(
                enabled=True,
                message="Build Success",
                color="good"
            )
        )
        self._merge_with_defaults(
            "blocks_message",
            lambda: SlackNotificationBlocksMessageConfig(
                enabled=False,
                blocks="[]",
                color="good"
            )
        )

class SlackNotificationOnFailureEventConfig(SlackNotificationEventConfig):
    def model_post_init(self, __context: Any) -> None:
        self._merge_with_defaults(
            "simple_message",
            lambda: SlackNotificationSimpleMessageConfig(
                enabled=True,
                message="Build Failed",
                color="danger"
            )
        )
        self._merge_with_defaults(
            "blocks_message",
            lambda: SlackNotificationBlocksMessageConfig(
                enabled=False,
                blocks="[]",
                color="danger"
            )
        )

class SlackNotificationOnUnstableEventConfig(SlackNotificationEventConfig):
    def model_post_init(self, __context: Any) -> None:
        self._merge_with_defaults(
            "simple_message",
            lambda: SlackNotificationSimpleMessageConfig(
                enabled=True,
                message="Build Unstable",
                color="warning"
            )
        )
        self._merge_with_defaults(
            "blocks_message",
            lambda: SlackNotificationBlocksMessageConfig(
                enabled=False,
                blocks="[]",
                color="warning"
            )
        )

class SlackNotificationOnExceptionEventConfig(SlackNotificationEventConfig):
    def model_post_init(self, __context: Any) -> None:
        self._merge_with_defaults(
            "simple_message",
            lambda: SlackNotificationSimpleMessageConfig(
                enabled=True,
                message="Build Failed ( Reason : ${err} )",
                color="danger"
            )
        )
        self._merge_with_defaults(
            "blocks_message",
            lambda: SlackNotificationBlocksMessageConfig(
                enabled=False,
                blocks="[]",
                color="danger"
            )
        )

class SlackNotificationsConfig(FeatureConfig):
    """Configuration model for Slack notifications."""
    channel: str
    message_template: str = None
    pre_build_step : SlackNotificationPreBuildStepEventConfig = SlackNotificationPreBuildStepEventConfig()
    on_success : SlackNotificationOnSuccessEventConfig = SlackNotificationOnSuccessEventConfig()
    on_failure: SlackNotificationOnFailureEventConfig = SlackNotificationOnFailureEventConfig()
    on_unstable: SlackNotificationOnUnstableEventConfig = SlackNotificationOnUnstableEventConfig()
    on_exception: SlackNotificationOnExceptionEventConfig = SlackNotificationOnExceptionEventConfig()
    webhook_credential_id: Optional[str] = None

    @field_validator('channel')
    @classmethod
    def validate_channel(cls, v):
        if not v.startswith('#') and not v.startswith('@'):
            raise ValueError('Channel must start with # or @')
        return v


class SlackNotificationsFeature(BaseFeature):
    """Feature for adding Slack notifications to Jenkins pipelines."""
    
    @property
    def feature_name(self) -> str:
        return "slack_notifications"
    
    def should_include(self, config: Dict[str, Any]) -> bool:
        return "slack_notifications" in config and config["slack_notifications"].get("channel")
    
    def get_config_model(self) -> BaseModel:
        return SlackNotificationsConfig