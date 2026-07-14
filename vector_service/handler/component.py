from pydantic import BaseModel
from .base import BaseHandler
from config import settings


class ComponentMetadata(BaseModel):
    name: str
    lib_name: str
    component_name: str
    group_id: int


class ComponentHandler(BaseHandler):
    @property
    def index_name(self) -> str:
        return f"{settings.es_index_prefix}component"

    def validate_metadata(self, metadata: dict) -> dict:
        return ComponentMetadata(**metadata).model_dump()
