from pydantic import BaseModel
from PyScripts.uepyscripts.ci.jenkins.features.base_feature import BaseFeature, register_feature

class SlackConfig(BaseModel):
    channel: str
    on_failure: bool = True

    @classmethod
    def from_config(cls, features: dict):
        return cls(**features.get("slack", {}))

@register_feature
class SlackFeature(BaseFeature):
    """Slack notifications"""
    name = "slack"
    dependencies = []
    
    def should_activate(self) -> bool:
        return self.config.slack.enabled