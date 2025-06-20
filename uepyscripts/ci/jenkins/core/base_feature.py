from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Type

from pydantic import BaseModel

from uepyscripts.ci.jenkins.core.feature_registry import FeatureRegistry
from uepyscripts.ci.jenkins.core.pipeline_config import PipelineConfig


class BaseFeature(ABC):
    """Base class for all pipeline features"""

    def __init_subclass__(cls, **kwargs):
        """Auto-register feature subclasses"""
        super().__init_subclass__(**kwargs)
        if hasattr(cls, 'feature_name') and cls.feature_name:
            FeatureRegistry().register_feature(cls)

    @property
    @abstractmethod
    def feature_name(self) -> str:
        """Unique identifier for this feature."""
        pass

    @property
    def dependencies(self) -> List[str]:
        """List of feature names this feature depends on."""
        return []
    
    @abstractmethod
    def should_include(self, config: Dict[str, Any]) -> bool:
        """Determine if this feature should be included based on config."""
        pass
    
    @abstractmethod
    def get_config_model(self) -> Type[BaseModel]:
        """Return the Pydantic model for validating this feature's config."""
        pass