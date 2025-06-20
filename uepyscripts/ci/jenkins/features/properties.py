from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, validator

from uepyscripts.ci.jenkins.core.base_feature import BaseFeature

class PropertiesConfig(BaseModel):
    """Configuration model for the pipeline properties."""
    items: List[str] = None

class PropertiesFeature(BaseFeature):
    """Feature for defining the pipeline properties."""
    
    @property
    def feature_name(self) -> str:
        return "properties"
    
    def should_include(self, config: Dict[str, Any]) -> bool:
        return "properties" in config
    
    def get_config_model(self) -> BaseModel:
        return PropertiesConfig