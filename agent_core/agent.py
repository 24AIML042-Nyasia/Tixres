from agent_utils import load_modules
from .utils import val_modules
from agent_db.models import cleanup_old_metrics
from agent_core.debug import print_registries ,request
from agent_utils.utils import load_os_details
from agent_core.auth import is_registered, register
from settings import DEBUG

def install():
    load_os_details()

    register()


def startup():
    # while not is_registered():
    #     register()

    load_modules()

    cleanup_old_metrics()

    # print(val_modules(request))
    if(DEBUG):
        print_registries()
    

    

