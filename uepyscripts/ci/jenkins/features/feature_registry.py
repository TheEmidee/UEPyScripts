from typing import Dict, Type

from uepyscripts import logger

class FeatureRegistry:
    """Registry for auto-discovering and managing features"""
    
    def __init__(self):
        self._features: Dict[str, Type['BaseFeature']] = {}

    def register(self, feature_class: Type['BaseFeature']) -> Type['BaseFeature']:
        """Register a feature class"""
        self._features[feature_class.name] = feature_class
        return feature_class

    def dump_available_features(self):
        logger.info("Available features:")
        for name, feature_class in self._features.items():
            logger.info(f"  - {name}: {feature_class.__doc__ or 'No description'}")

feature_registry = FeatureRegistry()