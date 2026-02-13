import logging 

logging.basicConfig(level=logging.INFO)

def get_logger(name : str = 'Agent Server'):
    return logging.getLogger(name )