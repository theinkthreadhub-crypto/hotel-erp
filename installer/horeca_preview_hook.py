"""Force the preview EXE to use isolated data and port by default.

Only bundled into HoReCa One test artifacts, never a production build.
"""
import os
import sys

if '--data' not in sys.argv:
    local = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
    preview_data = os.path.join(local, 'HoReCaOnePreview', 'Data')
    sys.argv.extend(['--data', preview_data])
if '--port' not in sys.argv:
    sys.argv.extend(['--port', '8161'])
