from abc import ABC, abstractmethod

class BaseModule(ABC):
    name: str
    version: str
    description: str
    functions: dict

    @property
    def module_id(self) -> str:
        return f"{self.name}_v{self.version}"

    @abstractmethod
    def register(self) -> dict:
        """Return function registry"""
        pass
