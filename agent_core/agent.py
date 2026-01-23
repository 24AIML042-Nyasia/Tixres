from agent_utils import load_modules
from .utils import val_modules
from agent_core.debug import print_registries ,request


def startup():
    load_modules()

    print(val_modules(request))

    print_registries()
    

    

