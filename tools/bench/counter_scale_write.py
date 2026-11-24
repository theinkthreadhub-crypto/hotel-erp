"""Counter side of one save on the JSON engine, on the real SetuStore (app_main.py): read the data file, write the whole
data (as every save does), the daily backup copy, and the auto backup (.json.gz). Synthetic data only. Development tool.

    python tools/bench/counter_scale_write.py <dir with setu-db.json>
"""
import gzip
import json
import os
import resource
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
os.environ.setdefault('SETU_BACKUP', 'off')
import app_main  # noqa: E402

d = sys.argv[1]
t = time.time(); st = app_main.SetuStore(d); load = time.time() - t
data = json.loads(st.raw)
data.setdefault('settings', {})['scaleCheck'] = int(time.time())
times = []
for i in range(3):
    data['settings']['scaleCheck'] = i
    t = time.time(); st.write(data); times.append(round(time.time() - t, 2))
    st._last_copy = 0
bk = [f for f in os.listdir(os.path.join(d, 'Backups')) if f.startswith('setu-')]
t = time.time(); gz = gzip.compress(open(st.path, 'rb').read(), 6); gzs = time.time() - t
print(json.dumps({'loadS': round(load, 2), 'saveS': times, 'dataFileMB': round(os.path.getsize(st.path) / 1048576, 1),
                  'dailyCopyMB': round(os.path.getsize(os.path.join(d, 'Backups', bk[0])) / 1048576, 1) if bk else None,
                  'autoBackupGzMB': round(len(gz) / 1048576, 1), 'autoBackupGzS': round(gzs, 1),
                  'peakRssMB': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)}, indent=1))
