from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class GeneratedBlocks:
    """Container for all generated code blocks."""
    blocks: Dict[str,List[str]] = field(default_factory=dict)

    def merge_with(self, other: 'GeneratedBlocks'):
        """Merge this instance with another GeneratedBlocks instance."""
        self.blocks |= other.blocks

def make_generated_blocks() -> GeneratedBlocks:
    blocks = GeneratedBlocks()
    blocks.blocks["libraries"] = []
    blocks.blocks["imports"] = []
    blocks.blocks["pre_build_steps"] = []
    blocks.blocks["on_build_unstable"] = []
    blocks.blocks["on_build_failure"] = []
    blocks.blocks["on_build_success"] = []
    blocks.blocks["post_build_steps"] = []
    blocks.blocks["on_exception_thrown"] = []
    blocks.blocks["on_finally"] = []
    blocks.blocks["additional_functions"] = []
    return blocks