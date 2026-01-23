from agent_utils import load_modules
from .utils import val_modules


def startup():
    load_modules()

    print(val_modules({'modules' : ['cpu']}))

    

