from agent_utils.registry import FUNCTION_REGISTRY, MODULE_REGISTRY
# request = {'modules' : ['cpu_v1.0.0'],
#             'metrics' : {
#                 'cpu_v1.0.0.usage' : 5,
#                 'cpu_v1.0.0.cores' : 10
#                        }
#                        }

request = {
    'modules': [
        'cpu_v1.0.0',
        'memory_v1.0.0',
        'disk_v1.0.0',
        'system_v1.0.0',
        'process_v1.0.0',
        'network_v1.0.0',
        'temperature_v1.0.0'
    ],
    'metrics': {
        # CPU Module
        'cpu_v1.0.0.usage_overall': 5,
        'cpu_v1.0.0.usage_per_core': 10,
        'cpu_v1.0.0.load_average': 15,
        'cpu_v1.0.0.temperature': 30,
        'cpu_v1.0.0.core_count': 3600,  # Once per hour (static)
        'cpu_v1.0.0.frequency': 10,
        
        # Memory Module
        'memory_v1.0.0.ram': 5,
        'memory_v1.0.0.swap': 10,
        
        # Disk Module
        'disk_v1.0.0.usage': 60,
        'disk_v1.0.0.io': 5,
        'disk_v1.0.0.partitions': 300,  # Every 5 minutes
        
        # System Module
        'system_v1.0.0.uptime': 60,
        'system_v1.0.0.info': 3600,  # Once per hour (static)
        'system_v1.0.0.users': 30,
        'system_v1.0.0.process_count': 10,
        
        # Process Module
        'process_v1.0.0.top_cpu': 10,
        'process_v1.0.0.top_memory': 15,
        'process_v1.0.0.zombie_count': 30,
        'process_v1.0.0.total_threads': 15,
        
        # Network Module
        'network_v1.0.0.io': 5,
        'network_v1.0.0.connections': 10,
        
        # Temperature Module
        'temperature_v1.0.0.sensors': 30,
        'temperature_v1.0.0.fans': 30,
        'temperature_v1.0.0.battery': 60
    }
}

def print_registries():
    print(MODULE_REGISTRY.keys())
    print(FUNCTION_REGISTRY.keys())