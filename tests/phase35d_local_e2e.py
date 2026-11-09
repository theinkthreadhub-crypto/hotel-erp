"""Phase 3.5d.1: real HTTP loopback E2E between the local Cloudflare Worker (wrangler dev --local / Miniflare)
and the real Python SQLite counter (SqliteSetuStore + OutboxSyncDispatcher + InboundSyncReceiver).

No mocks: every request goes over 127.0.0.1 HTTP to the Worker running in Miniflare.
Isolation: synthetic hotels created with a test-only ADMIN_KEY, temporary persistence folder, never production.

    python tests/phase35d_local_e2e.py           # needs cloud/node_modules (npm ci in cloud/)
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['SETU_BACKUP'] = 'off'
os.environ.setdefault('SETU_CLOUD_URL', 'http://127.0.0.1:9')   # the legacy client never reaches a real cloud
import app_main as A                     # noqa: E402
import setu_sqlite as S                  # noqa: E402
from sqlite_phase2b_test import migrated  # noqa: E402
from sqlite_phase2_test import sample_doc  # noqa: E402

CLOUD = os.path.join(ROOT, 'cloud')
WRANGLER = os.path.join(CLOUD, 'node_modules', '.bin', 'wrangler' + ('.cmd' if os.name == 'nt' else ''))
ADMIN_KEY = 'synthetic-local-only-' + os.urandom(4).hex()
DEAD = 'http://127.0.0.1:9'
if os.environ.get('SETU_REQUIRE_WRANGLER') == '1' and not os.path.exists(WRANGLER):
    raise SystemExit('SETU_REQUIRE_WRANGLER=1 but cloud/node_modules/.bin/wrangler is missing: the E2E must run, not skip')


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def http(base, method, path, body=None, headers=None, timeout=30):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, method=method, headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b'{}')
        except ValueError:
            return e.code, {'raw': raw[:200].decode(errors='replace')}


def bill(i, total=105):
    return {'id': f'lb-{i}', 'table': '', 'channel': 'Takeaway', 'mode': 'Cash',
            'items': [{'mid': 'm1', 'name': 'Dish 1', 'price': 100, 'qty': 1}],
            'sub': 100, 'tax': 5, 'total': total, 'date': '2026-11-09', 'time': '12:00', 'used': []}


@unittest.skipUnless(os.path.exists(WRANGLER), 'cloud/node_modules missing: run npm ci in cloud/ (SKIPPED, not passed)')
class WorkerCounterLoopback(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='horeca-35d-')
        cls.port = free_port()
        cls.base = f'http://127.0.0.1:{cls.port}'
        subprocess.run(['node', 'scripts/copy-assets.mjs'], cwd=CLOUD, check=True, stdout=subprocess.DEVNULL)
        cls.log = open(os.path.join(cls.tmp, 'wrangler.log'), 'w')
        cls.proc = subprocess.Popen([WRANGLER, 'dev', '--local', '--port', str(cls.port), '--ip', '127.0.0.1', '--log-level', 'error',
                                     '--persist-to', os.path.join(cls.tmp, 'state'), '--var', f'ADMIN_KEY:{ADMIN_KEY}'],
                                    cwd=CLOUD, stdout=cls.log, stderr=subprocess.STDOUT)
        cls.addClassCleanup(cls._stop)
        for _ in range(90):
            try:
                if http(cls.base, 'GET', '/api/ping', timeout=3)[0] in (200, 400, 404):
                    break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError('local Worker did not start: ' + open(os.path.join(cls.tmp, 'wrangler.log')).read()[-2000:])
        cls.hotels = {'B': cls.new_hotel('B')}

    @classmethod
    def new_hotel(cls, tag):
        s, j = http(cls.base, 'POST', '/api/admin/create', {'name': f'Loopback Hotel {tag}', 'owner': 'Test Owner', 'phone': '9876543210',
                                                              'password': 'Loop@Test2026x', 'businessType': 'restaurant', 'days': 30, 'paid': True},
                    {'X-Setu-Admin': ADMIN_KEY})
        assert s == 200 and j.get('syncKey'), (s, j)
        return j['code'], j['syncKey']

    @classmethod
    def _stop(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(10)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
        cls.log.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        # One counter per cloud hotel (as in a real install): the cloud keeps a monotonic version checkpoint
        self.code, self.key = self.new_hotel('A')
        d = sample_doc(3)
        d['settings']['hotelId'] = d['auth']['hotelId'] = self.code
        self.tag = os.urandom(4).hex()   # bill ids unique across tests (one cloud hotel is shared)
        self.dir = migrated(tempfile.mkdtemp(dir=self.tmp), d)
        self.store = A.SqliteSetuStore(self.dir)
        self.disp = S.OutboxSyncDispatcher(self.store, url=self.base, hotel=self.code, key=self.key, enabled=True, batch_size=50)

    def tearDown(self):
        self.store.sdb.close()

    def h(self, code=None, key=None):
        return {'X-Setu-Hotel': code or self.code, 'X-Setu-Sync': key or self.key, 'X-Setu-Caps': 'secure1'}

    def state(self):
        s, j = http(self.base, 'GET', '/api/sync/state', None, self.h())
        self.assertEqual(s, 200, j)
        return j

    def pending(self):
        return self.store.sdb.con().execute('SELECT COUNT(*) FROM sync_outbox WHERE sent_at IS NULL').fetchone()[0]

    def drain(self, rounds=10):
        last = None
        for _ in range(rounds):
            last = self.disp.dispatch_once()
            if self.pending() == 0 or last.get('status') != 'ok':
                break
        return last

    def settle(self, i, total=105):
        code, r = self.store.settle_bill({'idemKey': f'idem-{self.tag}-{i}', 'bill': bill(f'{self.tag}-{i}', total)})
        self.assertEqual(code, 200, r)
        return r

    # ---------------------------------------------------------------- outbound: counter -> Worker
    def test_01_bills_reach_worker_over_http_with_exact_acks(self):
        self.assertEqual(self.disp.is_activation_safe(), (True, 'OK'))
        before = self.state()['bills_count']
        for i in range(5):
            self.settle(i)
        res = self.drain()
        self.assertEqual(res['status'], 'ok', res)
        self.assertEqual(self.pending(), 0, 'every bill acknowledged or quarantined; nothing left retrying')
        st = self.state()
        acked = self.store.sdb.con().execute("SELECT COUNT(*) FROM sync_outbox WHERE sent_at > 0").fetchone()[0]
        held = self.store.sdb.con().execute("SELECT COUNT(*) FROM sync_outbox WHERE sent_at < 0").fetchone()[0]
        self.assertGreaterEqual(acked, 4)
        self.assertEqual(st['bills_count'] - before, acked, 'cloud stored exactly the acknowledged bills')
        self.assertEqual(acked + held, 5)

    def test_02_resend_of_committed_op_is_idempotent(self):
        self.settle(0)
        self.settle(1)
        self.drain()
        row = self.store.sdb.con().execute("SELECT payload FROM sync_outbox WHERE sent_at > 0 ORDER BY seq DESC LIMIT 1").fetchone()
        self.assertIsNotNone(row, 'needs at least one committed op')
        env = json.loads(row[0])
        before = self.state()
        s, j = http(self.base, 'POST', '/api/sync/ops', {'batch': [env]}, self.h())
        self.assertEqual(s, 200, j)
        res = j['results'][env['op_id']]
        self.assertIn(res['status'], ('committed', 'duplicate'), res)
        after = self.state()
        self.assertEqual(after['bills_count'], before['bills_count'], 'a repeated op never creates a second bill')

    def test_03_offline_then_reconnect_keeps_every_op(self):
        self.settle('warm')
        self.drain()
        self.disp.url = DEAD
        for i in range(4):
            self.settle(i)
        n = self.pending()
        res = self.disp.dispatch_once()
        self.assertEqual(res['status'], 'network_error', res)
        self.assertEqual(self.pending(), n, 'offline: nothing lost, nothing marked sent')
        self.disp.url = self.base
        before = self.state()['bills_count']
        self.drain()
        self.assertEqual(self.pending(), 0)
        acked = self.store.sdb.con().execute("SELECT COUNT(*) FROM sync_outbox WHERE sent_at > 0").fetchone()[0]
        self.assertEqual(self.state()['bills_count'] - before, acked)

    def test_04_wrong_key_and_other_hotel_refused(self):
        self.settle(0)
        n = self.pending()
        bad = S.OutboxSyncDispatcher(self.store, url=self.base, hotel=self.code, key='0' * 40, enabled=True)
        self.assertEqual(bad.dispatch_once()['status'], 'auth_error')
        code_b, key_b = self.hotels['B']
        s, _ = http(self.base, 'GET', '/api/sync/state', None, self.h(code=self.code, key=key_b))
        self.assertEqual(s, 401, "hotel B's key cannot read hotel A")
        s, j = http(self.base, 'GET', '/api/sync/inbound', None, self.h(code=code_b))
        self.assertEqual(s, 401, "hotel A's key routed to hotel B is refused")
        s, j = http(self.base, 'POST', '/api/sync/inbound/ack', {'hotel_id': code_b, 'event_ids': ['evt_1_x']}, self.h())
        self.assertEqual(s, 403, j)
        self.assertEqual(self.pending(), n, 'refused requests change nothing on the counter')

    def test_05_rejected_module_never_blocks_later_bills(self):
        # A save of a module the cloud does not ingest (menu) is rejected permanently. It must not sit at the head
        # of the queue forever and starve every later bill (batch_size 2 makes the starvation visible quickly).
        self.settle(0)
        self.drain()
        self.disp.batch_size = 2
        for i in range(3):
            with self.store.lock:
                menu = self.store.data()['menu']
                menu[0] = dict(menu[0], price=120 + i)
                code, r = self.store.apply_ops({'bv': self.store.version, 'ops': [{'k': 'menu', 'up': [menu[0]]}]}, 'local')
            self.assertEqual(code, 200, r)
        r = self.settle(1)
        before = self.state()['bills_count']
        self.drain(rounds=6)
        self.assertEqual(self.pending(), 0, 'queue drained: rejected ops held for review, not retried forever')
        self.assertEqual(self.state()['bills_count'] - before, 1, 'the bill after the rejected saves reached the cloud')
        held = self.store.sdb.con().execute("SELECT COUNT(*) FROM sync_conflicts WHERE reason = 'UNSUPPORTED_BUSINESS_MODULE'").fetchone()[0]
        self.assertGreaterEqual(held, 3, 'each rejected save is kept for Manager review with its payload')

    # ---------------------------------------------------------------- inbound: Worker -> counter (QR)
    def test_06_guest_qr_order_reaches_counter_review_queue_once(self):
        # Fixture: the Worker's guest menu reads the hotel document (legacy upload path); seed menu + settings only.
        with self.store.lock:
            d = self.store.data()
        s, cur = http(self.base, 'GET', '/api/db', None, self.h())
        self.assertEqual(s, 200, cur)
        s, j = http(self.base, 'POST', '/api/db', {'baseVersion': cur.get('version', 0), 'data': {'settings': d['settings'], 'menu': d['menu']}}, self.h())
        self.assertEqual(s, 200, j)
        s, j = http(self.base, 'POST', '/api/qr/table', {'table': 'T-5', 'action': 'new'}, self.h())
        self.assertEqual(s, 200, j)
        tok = j['tables']['T-5']['token']
        s, menu = http(self.base, 'GET', f'/api/guest/menu?t={tok}', None, {'X-Setu-Hotel': self.code})
        self.assertEqual(s, 200, menu)
        oid = 'loop' + os.urandom(5).hex()
        s, o = http(self.base, 'POST', '/api/guest/order', {'t': tok, 'id': oid, 'items': [{'mid': 'm1', 'qty': 2, 'price': 1}]}, {'X-Setu-Hotel': self.code})
        self.assertEqual(s, 200, o)
        s, again = http(self.base, 'POST', '/api/guest/order', {'t': tok, 'id': oid, 'items': [{'mid': 'm1', 'qty': 9}]}, {'X-Setu-Hotel': self.code})
        self.assertTrue(again.get('again'), again)
        rcv = S.InboundSyncReceiver(store=self.store, url=self.base, hotel=self.code, key=self.key, enabled=True)
        for _ in range(3):
            rcv.fetch_and_apply_once()
        q = self.store.query('inbound-qr', {'status': 'all'})
        rows = [r for r in q['rows'] if r['order_id'] == 'g' + oid]
        self.assertEqual(len(rows), 1, q)
        self.assertEqual(rows[0]['status'], 'pending')
        self.assertEqual(rows[0]['items'][0]['qty'], 2, 'the repeated order (qty 9) was not applied')
        menu_price = float(next(m for m in menu['items'] if m['id'] == 'm1')['price'])
        self.assertEqual(rows[0]['items'][0]['price'], menu_price, 'price comes from the menu, never the guest')
        self.assertEqual(self.state()['inbound_pending'], 0, 'counter acknowledged the event over HTTP')
        kots = [k for k in (self.store.data().get('kots') or []) if k.get('qr') == 'g' + oid]
        self.assertEqual(kots, [], 'a pending QR order never creates a KOT or touches the bill')


if __name__ == '__main__':
    unittest.main(verbosity=2)
