from abc import ABC , abstractmethod

class BaseAnomaly(ABC):
    @abstractmethod
    def detect_anomaly(self):
        pass