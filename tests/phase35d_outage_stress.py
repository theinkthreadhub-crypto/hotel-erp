"""Phase 3.5d.3: reproducible cloud-outage stress run for the SQLite counter (synthetic data only).

The real OutboxSyncDispatcher (+ InboundSyncReceiver) background threads run against an unreachable cloud while the
real SqliteSetuStore settles bills at a steady rate. Sampled every `--sample` seconds:
  * outbox pending == bills made during the outage (nothing lost, nothing marked sent)
  * process RSS (Linux /proc or psutil) and thread count (no leak, no thread growth)
  * settle latency (the POS is never starved by the sync threads)
  * cloud attempts (backoff, no busy loop)
Optional recovery: with --recover-url / --hotel / --key (e.g. a local `wrangler dev` hotel), the dispatcher is
pointed at the cloud at the end and must drain every pending op.

    python tests/phase35d_outage_stress.py --hours 24            # the full run (needs a machine that stays up 24 h)
    python tests/phase35d_outage_stress.py --minutes 10 --json out.json

The report states the ACTUAL completed duration. A shorter run is not evidence for 24 hours.
"""
import argparse
import json
import os
import statistics
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['SETU_BACKUP'] = 'off'
os.environ.setdefault('SETU_CLOUD_URL', 'http://127.0.0.1:9')
import app_main as A                      # noqa: E402
import setu_sqlite as S                   # noqa: E402
from sqlite_phase2b_test import migrated  # noqa: E402
from sqlite_phase2_test import sample_doc  # noqa: E402

DEAD = 'http://127.0.0.1:9'   # connection refused at once: the outage path without network timeouts


def rss_mb():
    try:
        with open('/proc/self/statm') as f:
            return int(f.read().split()[1]) * os.sysconf('SC_PAGE_SIZE') / 1048576
    except (OSError, ValueError, AttributeError):
        try:
            import psutil
            return psutil.Process().memory_info().rss / 1048576
        except ImportError:
            return None


def slope_per_hour(points):
    """Least-squares slope (MB per hour) of (seconds, MB) samples."""
    if len(points) < 3:
        return None
    xs, ys = [p[0] / 3600 for p in points], [p[1] for p in points]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den, 3) if den else None


def run(seconds, bill_every, sample, hotel, recover_url, key, poll, max_backoff):
    tmp = tempfile.mkdtemp(prefix='horeca-outage-')
    d = sample_doc(20)
    d['settings']['hotelId'] = d['auth']['hotelId'] = hotel
    store = A.SqliteSetuStore(migrated(tmp, d))
    attempts = {'post': 0, 'get': 0}

    def post(url, path, body, headers, timeout=15):
        attempts['post'] += 1
        return S.OutboxSyncDispatcher._default_http_post(url, path, body, headers, timeout)

    def get(url, path, headers, timeout=15):
        attempts['get'] += 1
        return S.InboundSyncReceiver._default_http_get(url, path, headers, timeout)

    disp = S.OutboxSyncDispatcher(store, url=DEAD, hotel=hotel, key=key or 'synthetic-outage-key', enabled=True,
                                  poll_interval=poll, max_backoff=max_backoff, http_post_fn=post)
    disp.inbound.url = DEAD
    disp.inbound.http_get_fn, disp.inbound.http_post_fn = get, post
    pending0 = store.sdb.con().execute('SELECT COUNT(*) FROM sync_outbox WHERE sent_at IS NULL').fetchone()[0]
    disp.start()
    t0 = time.time()
    made, lat, samples, errors = 0, [], [], []
    base_threads = threading.active_count()
    next_sample = t0
    try:
        while time.time() - t0 < seconds:
            ts = time.perf_counter()
            code, r = store.settle_bill({'idemKey': f'out-{made}', 'bill': {
                'id': f'out-{made}', 'table': '', 'channel': 'Takeaway', 'mode': 'Cash', 'items': [{'mid': 'm1', 'name': 'x', 'price': 100, 'qty': 1}],
                'sub': 100, 'tax': 5, 'total': 105, 'date': time.strftime('%Y-%m-%d'), 'time': time.strftime('%H:%M'), 'used': []}})
            lat.append((time.perf_counter() - ts) * 1000)
            if code != 200:
                errors.append(r)
            made += 1
            now = time.time()
            if now >= next_sample:
                pend = store.sdb.con().execute('SELECT COUNT(*) FROM sync_outbox WHERE sent_at IS NULL').fetchone()[0]
                samples.append({'t': round(now - t0, 1), 'rssMB': round(rss_mb() or 0, 1), 'threads': threading.active_count(),
                                'pending': pend, 'bills': made, 'posts': attempts['post'], 'gets': attempts['get'],
                                'dispatcherAlive': bool(disp._thread and disp._thread.is_alive()), 'state': disp.stats.get('state')})
                print(json.dumps(samples[-1]), flush=True)
                next_sample = now + sample
            time.sleep(bill_every)
        elapsed = time.time() - t0
        con = store.sdb.con()
        pending = con.execute('SELECT COUNT(*) FROM sync_outbox WHERE sent_at IS NULL').fetchone()[0]
        sent = con.execute('SELECT COUNT(*) FROM sync_outbox WHERE sent_at IS NOT NULL').fetchone()[0]
        bills_db = con.execute("SELECT COUNT(*) FROM bills WHERE id LIKE 'out-%'").fetchone()[0]
        recovery = None
        if recover_url:
            disp.url = recover_url
            disp.inbound.url = recover_url
            tr = time.time()
            disp.wake()
            while time.time() - tr < 600:
                left = con.execute('SELECT COUNT(*) FROM sync_outbox WHERE sent_at IS NULL').fetchone()[0]
                if left == 0:
                    break
                time.sleep(1)
            recovery = {'seconds': round(time.time() - tr, 1), 'pendingLeft': left,
                        'acked': con.execute('SELECT COUNT(*) FROM sync_outbox WHERE sent_at > 0').fetchone()[0],
                        'heldForReview': con.execute('SELECT COUNT(*) FROM sync_outbox WHERE sent_at < 0').fetchone()[0]}
    finally:
        disp.stop()
        store.sdb.close()
    half = [(s['t'], s['rssMB']) for s in samples[len(samples) // 2:] if s['rssMB']]
    lat_sorted = sorted(lat)
    res = {
        'requestedSeconds': seconds, 'completedSeconds': round(elapsed, 1), 'completedHours': round(elapsed / 3600, 3),
        'billsMade': made, 'billsInDatabase': bills_db, 'settleErrors': len(errors),
        'outboxPendingAtEnd': pending, 'outboxSentDuringOutage': sent, 'expectedPending': pending0 + made,
        'cloudPostAttempts': attempts['post'], 'cloudGetAttempts': attempts['get'],
        'rssStartMB': samples[0]['rssMB'] if samples else None, 'rssEndMB': samples[-1]['rssMB'] if samples else None,
        'rssSlopeSecondHalfMBperHour': slope_per_hour(half),
        'threadsStart': base_threads, 'threadsMax': max((s['threads'] for s in samples), default=None),
        'dispatcherAliveAtEnd': all(s['dispatcherAlive'] for s in samples[-1:]),
        'settleLatencyMs': {'median': round(statistics.median(lat), 2), 'p99': round(lat_sorted[int(len(lat) * 0.99) - 1], 2), 'max': round(lat_sorted[-1], 2)} if lat else None,
        'recovery': recovery, 'samples': samples,
    }
    checks = {
        'no bill lost': bills_db == made and not errors,
        'nothing marked sent while offline': sent == 0,
        'every bill pending in the outbox': pending == pending0 + made,
        'dispatcher thread alive': res['dispatcherAliveAtEnd'],
        'no thread growth': res['threadsMax'] is not None and res['threadsMax'] <= base_threads + 1,
        'POS not starved (p99 settle < 250 ms)': bool(lat) and res['settleLatencyMs']['p99'] < 250,
    }
    if recovery:
        checks['recovery drained the outbox'] = recovery['pendingLeft'] == 0
    res['checks'] = checks
    res['pass'] = all(checks.values())
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hours', type=float)
    ap.add_argument('--minutes', type=float)
    ap.add_argument('--bill-every', type=float, default=2.0, help='seconds between bills (default 2 s = 43,200 bills / 24 h)')
    ap.add_argument('--sample', type=float, default=60.0)
    ap.add_argument('--poll', type=float, default=5.0)
    ap.add_argument('--max-backoff', type=float, default=30.0)
    ap.add_argument('--hotel', default='OUTAGE01')
    ap.add_argument('--recover-url')
    ap.add_argument('--key')
    ap.add_argument('--json')
    a = ap.parse_args()
    seconds = (a.hours or 0) * 3600 + (a.minutes or 0) * 60 or 60
    res = run(seconds, a.bill_every, a.sample, a.hotel.upper(), a.recover_url, a.key, a.poll, a.max_backoff)
    summary = {k: v for k, v in res.items() if k != 'samples'}
    print(json.dumps(summary, indent=1))
    if a.json:
        with open(a.json, 'w') as f:
            json.dump(res, f, indent=1)
    sys.exit(0 if res['pass'] else 1)


if __name__ == '__main__':
    main()
