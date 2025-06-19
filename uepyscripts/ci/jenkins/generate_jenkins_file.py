from pathlib import Path
import sys
import yaml

from uepyscripts import logger
from uepyscripts.ci.jenkins.features.feature_registry import feature_registry
from uepyscripts.ci.jenkins.config.pipeline_config import PipelineConfig

def main():
    """Main CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Generate Jenkins pipeline from YAML config')
    parser.add_argument('config', type=Path, help='YAML configuration file')
    parser.add_argument('-o', '--output', type=Path, help='Output Jenkinsfile path')
    parser.add_argument('--validate-only', action='store_true', help='Only validate config')
    parser.add_argument('--list-features', action='store_true', help='List available features')
    
    args = parser.parse_args()
    
    if args.list_features:
        feature_registry.dump_available_features()
        return
    
    try:
        # generator = JenkinsfileGenerator()
        
        if args.validate_only:
            with open(args.config, 'r') as f:
                config_data = yaml.safe_load(f)
            config = PipelineConfig(**config_data)
            logger.info(f"✓ Configuration is valid")
            logger.info(f"  Pipeline: {config.name}")
            
            feature_registry.dump_available_features()

    #     else:
    #         output_path = args.output or Path("Jenkinsfile")
    #         content = generator.generate_from_config_file(args.config, output_path)
    #         print(f"✓ Generated Jenkinsfile: {output_path}")
            
    except Exception as e:
        logger.error(f"✗ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()