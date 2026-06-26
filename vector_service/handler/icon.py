from pydantic import BaseModel
from .base import BaseHandler


class IconMetadata(BaseModel):
    name: str
    description: str
    english_name: str
    category: str


class IconHandler(BaseHandler):
    index_name = "vec_icon"

    def validate_metadata(self, metadata: dict) -> dict:
        return IconMetadata(**metadata).model_dump()
