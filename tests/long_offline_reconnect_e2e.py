"""A counter PC that was offline for 15 days comes back online (real counter on the legacy JSON storage = v1.0 default,
real local Worker, synthetic hotel; never production).

  1. the counter is linked to the cloud and syncs;
  2. the cloud goes away ("no internet"); the counter keeps billing: 15 days of bills with split payments and credit
     notes are saved on the counter;
  3. the 30-day check: after 15 days the counter is NOT warned or locked (warning from day 20, lock from day 30, data safe);
  4. the cloud comes back: every bill reaches the cloud, totals match to the paisa, nothing doubled, the hotel is still
     active (the PC is not cut off) and the 30-day clock starts again;
  5. a second sync changes nothing (idempotent).

    python tests/long_offline_reconnect_e2e.py      # needs cloud/node_modules (npm ci in cloud/)
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phase35d_local_e2e import ADMIN_KEY, CLOUD, ROOT, WRANGLER, free_port, http  # noqa: E402

DAY = 86400
P = lambda v: int(round(float(v or 0) * 100))


def day(n_ago):
    return time.strftime('%Y-%m-%d', time.localtime(time.time() - n_ago * DAY))


def offline_bills(days=15, per_day=120):
    """Bills of `days` days, made while the cloud was unreachable (mixed modes, split payments)."""
    bills, no = [], 1000
    for d in range(days, 0, -1):
        for k in range(per_day):
            no += 1
            sub = 100 + (k % 7) * 35.5
            tax = round(sub * 0.05, 2)
            total = round(sub + tax)
            mode = ('Cash', 'UPI', 'Card', 'Split')[k % 4]
            b = {'id': f'off-{d}-{k}', 'no': no, 'date': day(d), 'time': '13:%02d' % (k % 60), 'channel': 'Dine-In', 'table': 'T-1',
                 'items': [{'mid': 'm1', 'name': 'Thali', 'price': sub, 'qty': 1}], 'sub': sub, 'disc': 0, 'taxable': sub, 'tax': tax,
                 'round': round(total - sub - tax, 2), 'total': total, 'gstRate': 5, 'mode': mode, 'idemKey': f'idem_off_{d}_{k}', 'used': []}
            if mode == 'Split':
                b['pays'] = [{'mode': 'Cash', 'amt': 50}, {'mode': 'UPI', 'amt': round(total - 50, 2)}]
            bills.append(b)
    return bills


@unittest.skipUnless(os.path.exists(WRANGLER), 'cloud/node_modules missing: run npm ci in cloud/ (SKIPPED, not passed)')
class LongOfflineReconnect(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='horeca-offline15-')
        cls.wport, cls.cport = free_port(), free_port()
        cls.W, cls.C = f'http://127.0.0.1:{cls.wport}', f'http://127.0.0.1:{cls.cport}'
        subprocess.run(['node', 'scripts/copy-assets.mjs'], cwd=CLOUD, check=True, stdout=subprocess.DEVNULL)
        cls.wlog = open(os.path.join(cls.tmp, 'wrangler.log'), 'w')
        cls.worker = cls.counter = None
        cls.start_worker()
        s, j = http(cls.W, 'POST', '/api/admin/create', {'name': 'Offline Fifteen', 'owner': 'Test Owner', 'phone': '9876543210',
                                                       'password': 'Loop@Test2026x', 'businessType': 'restaurant', 'days': 365, 'paid': True,
                                                       'mustChange': False}, {'X-Setu-Admin': ADMIN_KEY})
        assert s == 200, j
        cls.code, cls.key = j['code'], j['syncKey']
        cls.data = os.path.join(cls.tmp, 'counter')
        os.makedirs(cls.data)
        until = time.strftime('%Y-%m-%d', time.localtime(time.time() + 200 * DAY))
        doc = {'settings': {'hotelId': cls.code, 'name': 'Offline Fifteen', 'gst': 5, 'adminPin': '8642', 'cashierPin': '1357'},
               'auth': {'hotelId': cls.code, 'password': 'Loop@Test2026x', 'ownerName': 'Test Owner', 'isRegistered': True},
               'menu': [{'id': 'm1', 'name': 'Thali', 'price': 100}], 'bills': [], 'kots': [], 'txns': [], 'cnotes': [], 'staff': [],
               'seq': {'bill': 1000, 'kot': 0, 'cn': 0},
               'subscription': {'status': 'active', 'planName': 'QA', 'validUntil': until, 'usedKeys': [], 'lastSeen': int(time.time() * 1000)}}
        with open(os.path.join(cls.data, 'setu-db.json'), 'w') as f:
            json.dump({'version': 1, 'savedAt': 1, 'data': doc}, f)
        cls.start_counter()

    @classmethod
    def start_worker(cls):
        cls.worker = subprocess.Popen([WRANGLER, 'dev', '--local', '--port', str(cls.wport), '--ip', '127.0.0.1', '--log-level', 'error',
                                       '--persist-to', os.path.join(cls.tmp, 'state'), '--var', f'ADMIN_KEY:{ADMIN_KEY}'],
                                      cwd=CLOUD, stdout=cls.wlog, stderr=subprocess.STDOUT)
        for _ in range(90):
            try:
                if http(cls.W, 'GET', '/api/ping', timeout=3)[0] in (200, 400, 404):
                    return
            except OSError:
                time.sleep(1)
        raise RuntimeError('local Worker did not start')

    @classmethod
    def stop_worker(cls):
        cls.worker.send_signal(signal.SIGTERM)
        try:
            cls.worker.wait(10)
        except subprocess.TimeoutExpired:
            cls.worker.kill()
            cls.worker.wait(10)
        for _ in range(40):
            try:
                http(cls.W, 'GET', '/api/ping', timeout=1)
                time.sleep(0.5)
            except OSError:
                return

    @classmethod
    def start_counter(cls):
        env = {**os.environ, 'SETU_CLOUD_URL': cls.W, 'SETU_BACKUP': 'off'}
        env.pop('SETU_STORAGE', None)
        cls.counter = subprocess.Popen([sys.executable, 'app_main.py', '--server', '--port', str(cls.cport), '--data', cls.data],
                                       cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        for _ in range(120):
            try:
                if http(cls.C, 'GET', '/api/ping', timeout=2)[0] == 200:
                    break
            except OSError:
                time.sleep(0.25)
        with open(os.path.join(cls.data, "setu-launch.key")) as f:
            cls.launch = f.read().strip()

    @classmethod
    def stop_counter(cls):
        cls.counter.terminate()
        try:
            cls.counter.wait(10)
        except subprocess.TimeoutExpired:
            cls.counter.kill()

    @classmethod
    def tearDownClass(cls):
        for p in (cls.counter, cls.worker):
            if p and p.poll() is None:
                p.kill()
        cls.wlog.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ---- helpers ----
    def local(self):
        return {'X-Setu-Launch': self.launch}

    def counter_db(self):
        s, j = http(self.C, 'GET', '/api/db', None, self.local())
        self.assertEqual(s, 200, j)
        return j

    def cloud_db(self):
        s, j = http(self.W, 'GET', '/api/db', None, {'X-Setu-Hotel': self.code, 'X-Setu-Sync': self.key, 'X-Setu-Caps': 'secure1'})
        self.assertEqual(s, 200, j)
        return j['data']

    def ping(self):
        return http(self.C, 'GET', '/api/ping')[1]

    def wait_synced(self, n, timeout=120):
        t = time.time()
        while time.time() - t < timeout:
            try:
                if len(self.cloud_db().get('bills') or []) >= n:
                    return True
            except Exception:
                pass
            time.sleep(2)
        return False

    def set_ok_at(self, days_ago):
        self.stop_counter()
        p = os.path.join(self.data, 'setu-cloud-state.json')
        with open(p) as f:
            st = json.load(f)
        st['okAt'] = int((time.time() - days_ago * DAY) * 1000)
        with open(p, 'w') as f:
            json.dump(st, f)
        self.start_counter()

    # ---- the scenario (one test: the steps depend on each other) ----
    def test_fifteen_days_offline_then_reconnect(self):
        # 1. link and first sync
        s, j = http(self.C, 'POST', '/api/cloud', {'url': self.W, 'hotel': self.code, 'key': self.key, 'enabled': True}, self.local())
        self.assertEqual(s, 200, j)
        cur = self.counter_db()
        first = offline_bills(1, 3)
        for b in first:
            b['id'] = 'on-' + b['id']; b['idemKey'] += '_on'
        cur['data']['bills'] = first
        s, j = http(self.C, 'POST', '/api/db', {'baseVersion': cur['version'], 'data': cur['data']}, self.local())
        self.assertEqual(s, 200, j)
        self.assertTrue(self.wait_synced(3), 'first sync reached the cloud')
        for _ in range(30):                           # the vendor's part (plan, lock, 30-day check) reaches the counter
            if (self.counter_db()['data'].get('saas') or {}).get('tier'):
                break
            time.sleep(1)
        self.assertTrue((self.counter_db()['data'].get('saas') or {}).get('tier'), 'plan / lock settings came back from the cloud after the first sync')

        # 2. no internet for 15 days: bills keep being saved on the counter
        self.stop_worker()
        cur = self.counter_db()
        off = offline_bills(15, 120)
        cur['data']['bills'] = cur['data']['bills'] + off
        cur['data']['cnotes'] = [{'id': 'cn-off-1', 'no': 1, 'date': day(3), 'billId': off[10]['id'], 'billNo': off[10]['no'], 'taxable': 100, 'tax': 5,
                                  'total': 105, 'rate': 5, 'items': [{'k': 0, 'qty': 1, 'name': 'Thali', 'price': 100}], 'refund': 'Cash'}]
        cur['data']['seq']['cn'] = 1
        s, j = http(self.C, 'POST', '/api/db', {'baseVersion': cur['version'], 'data': cur['data']}, self.local())
        self.assertEqual(s, 200, j)
        n_counter = len(self.counter_db()['data']['bills'])
        self.assertEqual(n_counter, 3 + 15 * 120, 'every offline bill saved on the counter')

        # 3. the 30-day check while offline
        self.set_ok_at(15)
        g = self.ping().get('grace')
        self.assertTrue(g is not None and 14.9 <= g < 20, f'15 days offline: no warning yet (grace {g}; warning from 20, lock from 30)')
        self.set_ok_at(21)
        g21 = self.ping().get('grace')
        self.assertTrue(20 <= g21 < 30, f'day 21: warning band ({g21})')
        self.set_ok_at(31)
        g31 = self.ping().get('grace')
        self.assertGreaterEqual(g31, 30, 'day 31: lock band (billing data stays safe; internet or a key opens it)')
        self.assertEqual(len(self.counter_db()['data']['bills']), n_counter, 'nothing deleted while locked')

        # 4. internet back
        self.start_worker()
        self.assertTrue(self.wait_synced(n_counter, 180), 'every bill reached the cloud')
        time.sleep(4)
        cl, co = self.cloud_db(), self.counter_db()['data']
        self.assertEqual(len(cl['bills']), len(co['bills']), 'same number of bills')
        self.assertEqual(len({b['id'] for b in cl['bills']}), len(cl['bills']), 'no bill doubled on the cloud')
        self.assertEqual(len({b['no'] for b in cl['bills']}), len(cl['bills']), 'no bill number doubled on the cloud')
        tot = lambda L: (sum(P(b['total']) for b in L), sum(P(b['tax']) for b in L),
                         sum(P(p['amt']) for b in L for p in (b.get('pays') or [{'amt': b['total']}])))
        self.assertEqual(tot(cl['bills']), tot(co['bills']), 'bill totals, GST and payments match to the paisa')
        self.assertEqual([c['id'] for c in cl.get('cnotes') or []], ['cn-off-1'], 'the offline credit note arrived once')
        s, a = http(self.W, 'POST', '/api/admin/hotel', {'code': self.code}, {'X-Setu-Admin': ADMIN_KEY})
        self.assertEqual(s, 200, a)
        self.assertEqual(a.get('status'), 'active', 'the hotel is still active: the PC was not cut off')
        for _ in range(60):
            g = self.ping().get('grace')
            if g is not None and g < 1:
                break
            time.sleep(2)
        self.assertLess(g, 1, 'the 30-day clock started again after the sync')

        # 5. another sync round changes nothing
        v1 = len(self.cloud_db()['bills'])
        time.sleep(12)
        self.assertEqual(len(self.cloud_db()['bills']), v1, 'a repeated sync adds nothing')


if __name__ == '__main__':
    unittest.main(verbosity=2)
