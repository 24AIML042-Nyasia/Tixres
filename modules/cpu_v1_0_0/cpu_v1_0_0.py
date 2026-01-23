import asyncio

from modules.base import BaseModule

class CpuModule(BaseModule):
    name = "cpu"
    version = "1.0.0"
    description = "CPU related metrics"

    def __init__(self):
        self.functions = {
            "usage": self.get_usage,
            "cores": self.get_cores
        }

        self.metric_datatype = {
            "usage" : "float",
            "cores" : "int"
        }

    async def get_usage(self):
        return "42%"

    async def get_cores(self):
        return 8

    def register(self):
        return self.functions