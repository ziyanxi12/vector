from pydantic import BaseModel
from .base import BaseHandler


class ComponentMetadata(BaseModel):
    name: str
    canvas_name: str
    component_name: str
    domain: str


class ComponentHandler(BaseHandler):
    index_name = "vec_component"

    def validate_metadata(self, metadata: dict) -> dict:
        return ComponentMetadata(**metadata).model_dump()
