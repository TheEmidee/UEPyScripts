from abc import ABC
from pathlib import Path
from typing import List

from uepyscripts.ci.jenkins.config.pipeline_config import PipelineConfig
from uepyscripts.ci.jenkins.features.feature_registry import feature_registry

def register_feature(cls):
    feature_registry.register(cls)
    return cls

class BaseFeature(ABC):
    """Base class for all pipeline features"""
    
    name: str = ""  # Must be overridden
    dependencies: List[str] = []  # Feature names this depends on

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.template_dir = Path(__file__).parent / "templates" / "features"
    
    def __init_subclass__(cls, **kwargs):
        """Auto-register feature subclasses"""
        super().__init_subclass__(**kwargs)
        if cls.name:  # Only register if name is defined
            feature_registry.register(cls)