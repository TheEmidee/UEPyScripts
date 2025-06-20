from typing import Dict, Type

class FeatureRegistry:
    """Registry for auto-discovering and managing features"""
    _instance = None
    _features: Dict[str, Type['BaseFeature']] = {}
    _modules_loaded = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register_feature(cls, feature_class: Type['BaseFeature']):
        """Register a feature class"""
        cls._features[feature_class.feature_name] = feature_class                
        cls._modules_loaded = True

    @classmethod
    def get_all_features(cls) -> Dict[str, Type['BaseFeature']]:
        """Get all registered features."""
        return cls._features.copy()