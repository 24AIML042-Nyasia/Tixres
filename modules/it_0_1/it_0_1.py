from modules.base import BaseMetric

class CpuMetric(BaseMetric):
    NAME = "cpu"

    def collect(self):
        return {"cpu": 42}
