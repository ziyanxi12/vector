from fastapi import HTTPException
from .base import BaseHandler
from .component import ComponentHandler
from .icon import IconHandler

_registry: dict[str, BaseHandler] = {
    "component": ComponentHandler(),
    "icon": IconHandler(),
}


def get_handler(type_name: str) -> BaseHandler:
    handler = _registry.get(type_name)
    if handler is None:
        raise HTTPException(status_code=400, detail=f"Unknown type: {type_name}")
    return handler
