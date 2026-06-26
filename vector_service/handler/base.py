from abc import ABC, abstractmethod


class BaseHandler(ABC):
    index_name: str

    @abstractmethod
    def validate_metadata(self, metadata: dict) -> dict:
        pass
