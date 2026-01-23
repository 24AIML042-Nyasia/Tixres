from abc import ABC, abstractmethod

class BaseModule(ABC):
    name: str
    version: str
    description: str
    functions: dict
    metric_datatype : dict

    @abstractmethod
    def register(self) -> dict:
        """Return function registry"""
        pass