from pydantic import BaseModel
from typing import Any, Dict, Optional

class PipelineConfig(BaseModel):
    name: Optional[str] = "DefaultPipeline"
    features: Dict[str, Any] = {}