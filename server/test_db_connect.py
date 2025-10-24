import os
import traceback

# Optional: print environment used
print('NEO4J_URI=', os.getenv('NEO4J_URI'))
print('NEO4J_USER=', os.getenv('NEO4J_USER'))

from db import get_driver

try:
    d = get_driver()
    print('OK - driver:', type(d))
    try:
        d.verify_connectivity()
        print('verify_connectivity() ok')
    except Exception as e:
        print('verify_connectivity() raised:')
        traceback.print_exc()
except Exception:
    print('get_driver() failed:')
    traceback.print_exc()
