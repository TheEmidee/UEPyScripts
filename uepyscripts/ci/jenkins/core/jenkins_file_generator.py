from pathlib import Path
from typing import Any, Dict, List

import yaml

from uepyscripts.ci.jenkins.core.base_feature import BaseFeature
from uepyscripts.ci.jenkins.core.dependency_resolver import DependencyResolver
from uepyscripts.ci.jenkins.core.feature_registry import FeatureRegistry
from uepyscripts import logger

class JenkinsfileGenerator:
    """Main generator class that orchestrates the entire process."""

    def __init__(self, templates_dir: str = "templates"):
        self.templates_dir = Path(templates_dir)
        # self.template_lookup = TemplateLookup(directories=[str(self.templates_dir)])
        # self.base_template_path = "base_jenkinsfile.mako"
    
    def select_features(self, config: Dict[str, Any]) -> List[BaseFeature]:
        """Select and instantiate features based on configuration."""
        selected_features = []
        
        for feature_name, feature_class in FeatureRegistry().get_all_features().items():
            feature_instance = feature_class()
            if feature_instance.should_include(config):
                selected_features.append(feature_instance)
        
        return selected_features

    def generate_jenkinsfile(self, config_path: str, output_path: str) -> None:
        """Main method to generate a Jenkinsfile from configuration."""

        # Load configuration
        config = self.load_config(config_path)
        selected_features = self.select_features(config)
        logger.info(f"Selected {len(selected_features)} features: {[f.feature_name for f in selected_features]}")

        ordered_features = DependencyResolver.resolve_dependencies(selected_features)
        logger.info(f"Feature order (after dependency resolution): {[f.feature_name for f in ordered_features]}")

    def load_config(self, config_path: str) -> Dict[str, Any]:
        """Load and parse YAML configuration file."""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            raise ValueError(f"Failed to load config file '{config_path}': {e}")