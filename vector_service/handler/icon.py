from pydantic import BaseModel
from .base import BaseHandler
from config import settings


class IconMetadata(BaseModel):
    name: str
    description: str
    english_name: str
    category: str
    group_id: int


class IconHandler(BaseHandler):
    @property
    def index_name(self) -> str:
        return f"{settings.es_index_prefix}icon"

    def validate_metadata(self, metadata: dict) -> dict:
        return IconMetadata(**metadata).model_dump()
