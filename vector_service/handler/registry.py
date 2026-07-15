from fastapi import HTTPException
from .base import BaseHandler
from config import settings


class GenericHandler(BaseHandler):
    def __init__(self, type_name: str):
        self._type_name = type_name

    @property
    def index_name(self) -> str:
        return f"{settings.es_index_prefix}{self._type_name}"

    def validate_metadata(self, metadata: dict) -> dict:
        return metadata


def get_handler(type_name: str) -> BaseHandler:
    if settings.allow_dynamic_type:
        return GenericHandler(type_name)
    raise HTTPException(status_code=400, detail=f"Unknown type: {type_name}")
