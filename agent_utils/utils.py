import pkgutil
import importlib
import inspect
import os
import json

import socket
import platform

import modules
from modules.base import BaseModule
from agent_utils.registry import register_module
from settings import AGENT_FILE

def check_agent_file() -> bool:
    return os.path.exists(AGENT_FILE)

def load_modules():
    for _, module_name, _ in pkgutil.iter_modules(modules.__path__):
        # print(f"{modules.__name__}.{module_name}")
        module = importlib.import_module(f"{modules.__name__}.{module_name}")

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BaseModule) and obj is not BaseModule:
                register_module(obj())

def load_os_details():
    data ={ "hostname" : socket.gethostname(),
            "os" : platform.system() 
        }
    
    if check_agent_file():
        with open(AGENT_FILE, "w") as file:
            JSON = json.load(file)

            data.update(JSON)
    else: 
        os.makedirs(os.path.dirname(AGENT_FILE))

    with open(AGENT_FILE, "w") as file:
        json.dump(data, file)




