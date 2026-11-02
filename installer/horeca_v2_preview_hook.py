"""Standalone REVIEW EXE runtime hook. Only bundled by horeca-v2-windows-review.yml.

This fixture is NOT part of the production installer.
Never contacts a live cloud or reads customer databases.
"""
import os
import sys
import json
import time

_local = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
_preview_dir = os.path.join(_local, 'HoReCaOneOfflineDemoV2', 'Data')
if '--data' not in sys.argv:
    sys.argv.extend(['--data', _preview_dir])
if '--port' not in sys.argv:
    sys.argv.extend(['--port', '8162'])

# Disable all server-side cloud sync / registration for this review build.
os.environ['SETU_CLOUD_URL'] = 'http://127.0.0.1:9876'

# Create a demo hotel in this isolated folder ONLY ONCE.
# No fixed credentials are installed to production/customer databases.
if '--data' in sys.argv:
    i = sys.argv.index('--data')
    root = os.path.abspath(sys.argv[i + 1]) if i + 1 < len(sys.argv) else _preview_dir
else:
    root = _preview_dir
db = os.path.join(root, 'setu-db.json')
if not os.path.exists(db):
    import setu_security as SEC
    os.makedirs(root, exist_ok=True)
    demo_pw = 'Preview@2026'
    now = int(time.time() * 1000)
    d = {
        'auth': {
            'isRegistered': True, 'userId': 'owner',
            'hotelId': 'DEMOLOCAL', 'ownerName': 'Demo Manager',
            'status': 'active', 'phone': '', 'registeredAt': now
        },
        'settings': {
            'name': 'HoReCa One Demo Restaurant',
            'hotelId': 'DEMOLOCAL', 'owner': 'Demo Manager',
            'address': 'Offline Preview Only',
            'theme': 'horeca_light', 'dashStyle': 'modern',
            'gst': 5, 'gstScheme': 'regular', 'gstInclusive': False,
            'tables': ['T-1','T-2','T-3','T-4','T-5','T-6','Parcel'],
            'billPaper': 'thermal', 'kotPaper': 'thermal',
            'printMode': 'dialog',
            'zomatoEnabled': False, 'swiggyEnabled': False,
            'adminPinSet': True, 'cashierPinSet': True
        },
        'secure': {
            'v': 1, 'owner': SEC.hash_secret(demo_pw),
            'admin': SEC.hash_secret(demo_pw),
            'cashier': SEC.hash_secret('DemoCashier@2026'),
            'staff': {}
        },
        'subscription': {
            'status': 'active', 'planName': 'Offline Preview Only',
            'validUntil': '2030-12-31', 'isLifetime': False,
            'registeredEntity': 'Aghanya Devanya Enterprises',
            'usedKeys': [], 'history': []
        },
        'menu': [
            {'id':'dm1','cat':'Soups','name':'Tomato Soup','price':99},
            {'id':'dm2','cat':'Starters','name':'Paneer Tikka','price':229},
            {'id':'dm3','cat':'Main Course','name':'Paneer Butter Masala','price':259},
            {'id':'dm4','cat':'Main Course','name':'Dal Tadka','price':169},
            {'id':'dm5','cat':'Breads','name':'Butter Naan','price':49},
            {'id':'dm6','cat':'Rice','name':'Jeera Rice','price':149},
            {'id':'dm7','cat':'Beverages','name':'Fresh Lime Soda','price':89},
            {'id':'dm8','cat':'Desserts','name':'Gulab Jamun','price':79}
        ],
        'stock': [], 'moves': [], 'bills': [], 'txns': [], 'cash': {},
        'kaccha': {}, 'onlineOrders': [], 'kots': [], 'staff': [],
        'att': {}, 'outlets': {}, 'reservations': [],
        'sessions': [], 'orders': [], 'cnotes': [], 'demoCleanupDone': True,
        'seq': {'bill':0, 'kot':0, 'cn':0}
    }
    # Store format expected by app_main.SetuStore. Atomic creation; never overwrite.
    try:
        with open(db, 'x', encoding='utf-8') as f:
            json.dump({'version': 1, 'savedAt': now, 'data': d}, f, ensure_ascii=False)
    except FileExistsError:
        pass
