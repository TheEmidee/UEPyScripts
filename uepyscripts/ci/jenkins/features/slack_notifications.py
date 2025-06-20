from typing import Any, Dict, Optional
from pydantic import BaseModel, validator

from uepyscripts.ci.jenkins.core.base_feature import BaseFeature

class SlackNotificationsConfig(BaseModel):
    """Configuration model for Slack notifications."""
    channel: str
    on_success: bool = True
    on_failure: bool = True
    on_start: bool = False
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
    
    # @property
    # def dependencies(self) -> List[str]:
    #     return ["pipeline_utilities"]  # Depends on utility functions
    
    def should_include(self, config: Dict[str, Any]) -> bool:
        return "slack_notifications" in config and config["slack_notifications"].get("channel")
    
    def get_config_model(self) -> BaseModel:
        return SlackNotificationsConfig