from uepyscripts.internal.project import resolve_project
from uepyscripts.internal.engine import resolve_engine
from uepyscripts.internal.config import resolve_config

project = resolve_project()
engine = resolve_engine(project)
config = resolve_config(project)