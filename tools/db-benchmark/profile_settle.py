"""Profile native bill settle in-process on a migrated folder (development tool).

    python3 tools/db-benchmark/profile_settle.py <migratedDataFolder> [n]
"""
import cProfile
import os
import pstats
import sys
import threading
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)
import app_main  # noqa: E402

folder, n = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 200
t0 = time.time()
store = app_main.SqliteSetuStore(folder)
print('open', round(time.time() - t0, 1), 's; bills', len(store._doc['bills']))


def bill(i):
    return {'id': f'prof-{i}-{time.time_ns()}', 'table': '', 'channel': 'Takeaway', 'mode': 'Cash', 'items': [{'mid': 'mnu1', 'name': 'x', 'price': 100, 'qty': 1}],
            'sub': 100, 'tax': 5, 'total': 105, 'date': '2026-01-05', 'time': '13:00', 'used': [{'sid': 'stk1', 'qty': 0.25}]}


# warm up
for i in range(20):
    store.settle_bill({'idemKey': f'warm-{i}-{time.time_ns()}', 'bill': bill(i)})
lat = []
pr = cProfile.Profile()
pr.enable()
for i in range(n):
    t = time.perf_counter()
    code, r = store.settle_bill({'idemKey': f'p-{i}-{time.time_ns()}', 'bill': bill(i)})
    lat.append((time.perf_counter() - t) * 1000)
    assert code == 200, r
pr.disable()
lat.sort()
print('settle in-process: p50 %.1f ms, p95 %.1f ms' % (lat[len(lat) // 2], lat[int(len(lat) * .95)]))
pstats.Stats(pr).sort_stats('cumulative').print_stats(18)
# threads: 100 at once
lat2, lk = [], threading.Lock()


def w(k):
    for j in range(4):
        t = time.perf_counter()
        store.settle_bill({'idemKey': f't-{k}-{j}-{time.time_ns()}', 'bill': bill(k * 10 + j)})
        with lk:
            lat2.append((time.perf_counter() - t) * 1000)
t1 = time.time()
ts = [threading.Thread(target=w, args=(k,)) for k in range(100)]
[t.start() for t in ts]
[t.join() for t in ts]
lat2.sort()
print('100 threads in-process: %d bills in %.1f s = %.1f/s, p50 %.0f ms, p95 %.0f ms' % (len(lat2), time.time() - t1, len(lat2) / (time.time() - t1), lat2[len(lat2) // 2], lat2[int(len(lat2) * .95)]))
