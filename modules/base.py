from abc import ABC, abstractmethod

class BaseMetric(ABC):
    NAME: str

    @abstractmethod
    def collect(self):
        pass
