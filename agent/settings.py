DEBUG = True

METRIC_REGEX_PATTERN = r'^(?P<metric>[a-zA-Z]+)_v(?P<version>\d+\.\d+\.\d+)\.(?P<unit>[a-zA-Z_]+)$'

#e.g. temperature_v1.0.0.battery - module name - temperature , module version - 1.0.0 , function name - battery