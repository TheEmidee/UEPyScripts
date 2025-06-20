from abc import ABC, abstractmethod
from typing import Any, Dict, List, Type
from pydantic import BaseModel, ValidationError
from mako.lookup import TemplateLookup

from uepyscripts.ci.jenkins.core.pipeline_config import PipelineConfig
from uepyscripts.ci.jenkins.core.generated_blocks import GeneratedBlocks, make_generated_blocks
from uepyscripts.ci.jenkins.core.template_context import TemplateContext
from uepyscripts.ci.jenkins.core.feature_registry import FeatureRegistry

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
    
    @property
    def template_path(self) -> str:
        """Path to the Mako template file for this feature."""
        return f"{self.feature_name}.mako"
    
    @abstractmethod
    def should_include(self, config: Dict[str, Any]) -> bool:
        """Determine if this feature should be included based on config."""
        pass
    
    @abstractmethod
    def get_config_model(self) -> Type[BaseModel]:
        """Return the Pydantic model for validating this feature's config."""
        pass

    def get_feature_config(self, full_config: PipelineConfig) -> Dict[str, Any]:
        """Extract and validate this feature's config from the full config."""
        feature_config = full_config.features.get(self.feature_name, {})
        
        config_model = self.get_config_model()
        try:
            validated = config_model(**feature_config)
            return validated.dict()
        except ValidationError as e:
            raise ValueError(f"Invalid config for feature '{self.feature_name}': {e}")
        
    def render_blocks(self, context: TemplateContext, template_lookup: TemplateLookup) -> GeneratedBlocks:
        """Render all template blocks for this feature."""
        try:
            template = template_lookup.get_template(self.template_path)
        except Exception as e:
            raise FileNotFoundError(f"Template not found for feature '{self.feature_name}': {self.template_path}")
        
        blocks = make_generated_blocks()

        for block_type, block_value in blocks.blocks.items():
            try:
                rendered = template.get_def(block_type).render(**context.__dict__)
                if rendered.strip():
                    block_value.append(rendered.strip())
            except AttributeError as e:
                # Block not defined in template - that's OK
                pass
            except Exception as e:
                print(f"Warning: Error rendering {block_type} for {self.feature_name}: {e}")
        
        return blocks