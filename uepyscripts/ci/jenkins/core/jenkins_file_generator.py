from pathlib import Path
import re
from typing import Any, Dict, List
from mako.lookup import TemplateLookup

import yaml

from uepyscripts import logger
from uepyscripts.ci.jenkins.core.template_context import TemplateContext
from uepyscripts.ci.jenkins.core.pipeline_config import PipelineConfig
from uepyscripts.ci.jenkins.core.generated_blocks import GeneratedBlocks, make_generated_blocks
from uepyscripts.ci.jenkins.core.base_feature import BaseFeature
from uepyscripts.ci.jenkins.core.dependency_resolver import DependencyResolver
from uepyscripts.ci.jenkins.core.feature_registry import FeatureRegistry

class JenkinsfileGenerator:
    """Main generator class that orchestrates the entire process."""

    def __init__(self, templates_dir: str = "templates"):
        self.templates_dir = Path(templates_dir)
        self.template_lookup = TemplateLookup( directories=[str(self.templates_dir)] )
        self.base_template_path = "base_jenkinsfile.mako"

    def generate_jenkinsfile(self, config_path: str, output_path: str) -> None:
        """Main method to generate a Jenkinsfile from configuration."""

        # Load configuration
        config = self.load_config(config_path)
        selected_features = self.select_features(config)
        logger.info(f"Selected {len(selected_features)} features: {[f.feature_name for f in selected_features]}")

        ordered_features = DependencyResolver.resolve_dependencies(selected_features)
        logger.info(f"Feature order (after dependency resolution): {[f.feature_name for f in ordered_features]}")

        all_blocks = make_generated_blocks()
        global_values = {
            'pipeline_name': config.name,
            'generator_version': '1.0.0'
        }

        for feature in ordered_features:
            try:
                feature_config = feature.get_feature_config(config)
                context = TemplateContext(
                    full_config=config,
                    feature_config=feature_config,
                    global_values=global_values,
                    pipeline_name=config.name
                )

                blocks = feature.render_blocks(context, self.template_lookup)

                # Merge blocks
                all_blocks.merge_with(blocks)

            except Exception as e:
                raise RuntimeError(f"Failed to process feature '{feature.feature_name}': {e}")

        self.render_final_jenkinsfile(all_blocks, config, global_values, output_path)

    def load_config(self, config_path: str) -> PipelineConfig:
        """Load and parse YAML configuration file."""
        try:
            with open(config_path, 'r') as f:
                yaml_contents = yaml.safe_load(f)
                return PipelineConfig(**yaml_contents)
        except Exception as e:
            raise ValueError(f"Failed to load config file '{config_path}': {e}")

    def select_features(self, config: PipelineConfig) -> List[BaseFeature]:
        """Select and instantiate features based on configuration."""
        selected_features = []
        
        for feature_name, feature_class in FeatureRegistry().get_all_features().items():
            feature_instance = feature_class()
            if feature_instance.should_include(config.features):
                selected_features.append(feature_instance)

        return selected_features
    
    def render_final_jenkinsfile(self, blocks: GeneratedBlocks, config: PipelineConfig, global_values: Dict[str, Any], output_path: str) -> None:
        """Render the final Jenkinsfile using the base template."""
        try:
            base_template = self.template_lookup.get_template(self.base_template_path)
        except Exception as e:
            raise FileNotFoundError(f"Base template not found: {self.base_template_path}")

        try:
            d = {k: "\n".join(v or []) for k, v in blocks.blocks.items()}
            rendered = base_template.render_unicode(**d).strip().encode('utf-8', 'replace')

        except Exception as e:
            raise RuntimeError(f"Failed to render base template: {e}")
        
        # Write to output file
        with open(output_path, 'wb') as f:
            f.write(rendered)