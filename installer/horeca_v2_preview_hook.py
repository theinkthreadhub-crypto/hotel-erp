"""Isolated test-only Windows EXE runtime defaults for HoReCa One V2.
This file is never bundled in the customer production installer.
"""
import os
import sys
if '--data' not in sys.argv:
    local = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
    sys.argv.extend(['--data', os.path.join(local, 'HoReCaOneUIDemo', 'Data')])
if '--port' not in sys.argv:
    sys.argv.extend(['--port', '8162'])
# Do not contact the live Setu Cloud from a visual preview with demo records.
os.environ['SETU_CLOUD_URL'] = 'http://127.0.0.1:9876'
