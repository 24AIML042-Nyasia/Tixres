from abc import ABC , abstractmethod

class BaseAnomaly(ABC):
    detector_name = ''
    @abstractmethod
    def detect_anomaly(self):
        pass