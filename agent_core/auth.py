import requests
import json
import os

from settings import AGENT_FILE , SERVER_URL , AGENT_VERSION
from agent_utils.utils import load_os_details, check_agent_file

def is_registered():
    if check_agent_file():
        try:
            with open(AGENT_FILE , 'r') as file:
                data = json.load(file)

                if data['agentId'] == '':
                    return False
                else:
                    return True
            
        except:
            return False
        
    else:
        load_os_details()

        return False

def register():
    payload = {
        'agent_version' : AGENT_VERSION
    } 

    if not check_agent_file():
        os.makedirs(os.path.dirname(AGENT_FILE))

    with open(AGENT_FILE, "r") as file:
        data = json.load(file)
        payload.update(data)

    r = requests.post(SERVER_URL + "api_v1_0/agents/register", json=payload)
    data = r.json()

    with open(AGENT_FILE, "w") as file:
        json.dump(data, file)