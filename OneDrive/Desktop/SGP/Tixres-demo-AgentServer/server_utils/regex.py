import re
from settings import METRIC_REGEX_PATTERN

pattern = re.compile(METRIC_REGEX_PATTERN)

def check_metric_pattern(key : str):
    match = pattern.match(key)
        
    if match:
        return {
            'Metric': match.group('metric'),
            'Version': match.group('version'),
            'Unit': match.group('unit')
        }
    
    return {'Metric' : 'Not matched'}
            