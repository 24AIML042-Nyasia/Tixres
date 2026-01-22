import os
import importlib

package_name = __name__
package_path = os.path.dirname(__file__)

for filename in os.listdir(package_path):
    if filename.endswith(".py") and filename != "__init__.py":
        module_name = filename[:-3]
        
        importlib.import_module(f"{package_name}.{module_name}")
