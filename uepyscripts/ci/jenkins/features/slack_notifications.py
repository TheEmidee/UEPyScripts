from abc import ABC
from typing import Any, Dict, Optional
from pydantic import BaseModel, validator

from uepyscripts.ci.jenkins.core.base_feature import BaseFeature

class SlackNotificationMessageConfig(BaseModel,ABC):
    enabled: bool = False
    message_color : str = "#0000FF"
    message_template : str = ""

class SlackNotificationPreBuildStepEventConfig(SlackNotificationMessageConfig):
    enabled: bool = True
    message_color : str = "#0000FF"
    message_template : str = "Build Started"

class SlackNotificationOnSuccessEventConfig(SlackNotificationMessageConfig):
    enabled: bool = True
    message_color : str = "good"
    message_template : str = "Build Success"

class SlackNotificationOnFailureEventConfig(SlackNotificationMessageConfig):
    enabled: bool = True
    message_color : str = "danger"
    message_template : str = "Build Failed"

class SlackNotificationOnUnstableEventConfig(SlackNotificationMessageConfig):
    enabled: bool = True
    message_color : str = "warning"
    message_template : str = "Build Unstable"

class SlackNotificationOnExceptionEventConfig(SlackNotificationMessageConfig):
    enabled: bool = True
    message_color : str = "danger"
    message_template : str = "Build Failed ( Reason : ${err} )"

class SlackNotificationsConfig(BaseModel):
    """Configuration model for Slack notifications."""
    channel: str
    pre_build_step : SlackNotificationPreBuildStepEventConfig = SlackNotificationPreBuildStepEventConfig()
    on_success : SlackNotificationOnSuccessEventConfig = SlackNotificationOnSuccessEventConfig()
    on_failure: SlackNotificationOnFailureEventConfig = SlackNotificationOnFailureEventConfig()
    on_unstable: SlackNotificationOnUnstableEventConfig = SlackNotificationOnUnstableEventConfig()
    on_exception: SlackNotificationOnExceptionEventConfig = SlackNotificationOnExceptionEventConfig()
    message_template : str = "String full_message = message + \" : ${env.JOB_NAME} - ${env.CHANGE_BRANCH} #${env.BUILD_NUMBER} (<${env.BUILD_URL}|Open>)\""
    webhook_credential_id: Optional[str] = None
    
    @validator('channel')
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