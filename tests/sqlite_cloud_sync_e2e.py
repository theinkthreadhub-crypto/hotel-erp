"""Phase 3 (P3-1): a SQLite counter, the REAL program (app_main.py --server), linked to a local Worker, syncs with the
cloud while it runs: bills as ops into the cloud sync tables (owner reports), everything else (settings, menu, ...) as
the small document without bills, and the vendor's part (message / lock / plan) comes back to the counter.
A hotel moved from JSON keeps its old cloud bills.

Local Worker (Miniflare), synthetic hotels, test-only ADMIN_KEY, temporary folders. Never production.

    python tests/sqlite_cloud_sync_e2e.py     # needs cloud/node_modules (npm ci in cloud/)
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phase35d_local_e2e import ADMIN_KEY, ROOT, WRANGLER, LoopbackBase, free_port, http  # noqa: E402
from sqlite_phase2_test import sample_doc  # noqa: E402
from sqlite_phase2b_test import migrated  # noqa: E402

ADMIN = {'X-Setu-Admin': ADMIN_KEY}


def wait(fn, secs=90, every=0.5):
    end = time.time() + secs
    last = None
    while time.time() < end:
        last = fn()
        if last:
            return last
        time.sleep(every)
    return last


@unittest.skipUnless(os.path.exists(WRANGLER), 'cloud/node_modules missing: run npm ci in cloud/ (SKIPPED, not passed)')
class SqliteCounterCloudSync(LoopbackBase):
    def setUp(self):
        self.code, self.key = self.new_hotel('S')
        s, j = http(self.base, 'POST', '/api/login', {'pin': 'Loop@Test2026x'}, {'X-Setu-Hotel': self.code})
        self.assertEqual(s, 200, j)
        self.owner = {'X-Setu-Hotel': self.code, 'X-Setu-Token': j['token']}
        self.procs = []

    def tearDown(self):
        if os.environ.get('P3_DEBUG'):
            for d in getattr(self, 'dirs', []):
                lp = os.path.join(d, 'setu-server.log')
                if os.path.exists(lp):
                    print('--- counter log', d, '\n' + open(lp, encoding='utf-8').read()[-3000:], file=sys.stderr)
        for p in self.procs:
            p.kill()
            p.wait(10)

    def counter(self, doc):
        d = migrated(tempfile.mkdtemp(dir=self.tmp), doc)
        self.dirs = getattr(self, 'dirs', []) + [d]
        with open(os.path.join(d, 'setu-cloud.json'), 'w', encoding='utf-8') as f:
            json.dump({'url': self.base, 'hotel': self.code, 'key': self.key, 'enabled': True}, f)
        tok = 'p3-test-' + os.urandom(6).hex()
        with open(os.path.join(d, 'setu-devices.json'), 'w', encoding='utf-8') as f:
            json.dump({tok: 'admin'}, f)
        port = free_port()
        p = subprocess.Popen([sys.executable, 'app_main.py', '--server', '--port', str(port), '--data', d], cwd=ROOT,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             env={**os.environ, 'SETU_BACKUP': 'off', 'SETU_CLOUD_URL': self.base})
        self.procs.append(p)
        cu = f'http://127.0.0.1:{port}'
        self.assertTrue(wait(lambda: self._up(cu), 60), 'counter started')
        return cu, {'X-Setu-Token': tok}, d

    @staticmethod
    def _up(cu):
        try:
            return http(cu, 'GET', '/api/ping', timeout=2)[0] == 200
        except OSError:
            return False

    def cloud_doc(self):
        s, j = http(self.base, 'GET', '/api/db', None, {'X-Setu-Hotel': self.code, 'X-Setu-Sync': self.key, 'X-Setu-Caps': 'secure1'})
        self.assertEqual(s, 200, j)
        return j

    def sales(self):
        s, j = http(self.base, 'GET', '/api/reports/sales', None, self.owner)
        self.assertEqual(s, 200, j)
        return j['summary']

    def doc(self, bills=3):
        d = sample_doc(bills)
        d['settings']['hotelId'] = d['auth']['hotelId'] = self.code
        d['menu'] = [{'id': 'm1', 'name': 'Paneer Tikka', 'price': 280, 'cat': 'Starters'}, {'id': 'm2', 'name': 'Dal Makhani', 'price': 220, 'cat': 'Main'}]
        return d

    def settle(self, cu, h, i, total=105):
        b = {'id': f'p3-{self.code}-{i}', 'table': '', 'channel': 'Takeaway', 'mode': 'Cash', 'items': [{'mid': 'm1', 'name': 'Paneer Tikka', 'price': 100, 'qty': 1}],
             'sub': 100, 'tax': 5, 'total': total, 'date': time.strftime('%Y-%m-%d'), 'time': '12:00', 'used': []}
        s, r = http(cu, 'POST', '/api/bill/settle', {'idemKey': f'idem-p3-{self.code}-{i}', 'bill': b}, h)
        self.assertEqual(s, 200, r)
        return r

    def test_01_document_without_bills_and_bills_as_ops(self):
        cu, h, _ = self.counter(self.doc(3))
        # The document (settings, menu) reaches the cloud, without the bill history
        doc = wait(lambda: (lambda j: j if j.get('version') and (j['data'].get('menu') or []) else None)(self.cloud_doc()))
        self.assertTrue(doc, 'the counter uploaded its document')
        self.assertEqual([m['name'] for m in doc['data']['menu']], ['Paneer Tikka', 'Dal Makhani'], 'menu in the cloud (table QR menu)')
        self.assertEqual(doc['data'].get('bills') or [], [], 'no bill history in the cloud document')
        # Bills reach the cloud sync tables (owner reports)
        before = self.sales()['bill_count']
        for i in range(5):
            self.settle(cu, h, i)
        got = wait(lambda: self.sales()['bill_count'] >= before + 5)
        self.assertTrue(got, f"5 new bills in the owner's cloud report (was {before}, now {self.sales()['bill_count']})")
        s, st = http(cu, 'GET', '/api/q/status', None, h)
        self.assertEqual(s, 200, st)
        self.assertIn('Phase 3', st['cloudSync'])
        self.assertTrue(wait(lambda: http(cu, 'GET', '/api/q/status', None, h)[1]['outboxPending'] == 0), 'nothing left to send')
        self.assertEqual(st['cloudOps']['errors'], 0, st['cloudOps'])

    def test_02_vendor_message_reaches_the_sqlite_counter(self):
        cu, h, _ = self.counter(self.doc(2))
        self.assertTrue(wait(lambda: self.cloud_doc().get('version')), 'linked and uploaded')
        s, r = http(self.base, 'POST', '/api/admin/hotel', {'code': self.code, 'update': {'notice': {'t': 'Please renew by Friday', 'lv': 1}}}, ADMIN)
        self.assertEqual(s, 200, r)
        def notice():
            s2, j = http(cu, 'GET', '/api/db', None, h)
            return ((j.get('data') or {}).get('saas') or {}).get('notice') if s2 == 200 else None
        n = wait(notice, 120)
        self.assertTrue(n, 'the Super Admin message reached the counter')

    def test_03_old_cloud_bills_kept_after_moving_to_sqlite(self):
        # The hotel's cloud copy from its JSON time holds bills; the SQLite counter must never remove them
        old = self.doc(0)
        old['bills'] = [{'id': f'old-{i}', 'no': i + 1, 'date': '2026-01-05', 'time': '10:00', 'total': 210, 'sub': 200, 'tax': 10, 'mode': 'Cash',
                         'items': [{'mid': 'm2', 'name': 'Dal Makhani', 'price': 200, 'qty': 1}], 'used': []} for i in range(4)]
        s, j = http(self.base, 'POST', '/api/db', {'baseVersion': 0, 'force': False, 'data': old},
                    {'X-Setu-Hotel': self.code, 'X-Setu-Sync': self.key, 'X-Setu-Caps': 'secure1'})
        self.assertEqual(s, 200, j)
        self.assertEqual(len(self.cloud_doc()['data'].get('bills') or []), 4, 'precondition: the cloud holds the JSON-time bills')
        cu, h, _ = self.counter(self.doc(2))
        for i in range(2):
            self.settle(cu, h, 100 + i)
        self.assertTrue(wait(lambda: self.cloud_doc()['version'] > 1 and self.cloud_doc()['data']['settings'].get('name') == self.doc()['settings'].get('name')),
                        'the counter saved its document')
        time.sleep(3)
        ids = [b['id'] for b in self.cloud_doc()['data'].get('bills') or []]
        self.assertEqual(sorted(ids), [f'old-{i}' for i in range(4)], 'the JSON-time cloud bills are all still there')

    def test_05_counter_bill_history_never_shrinks_while_syncing(self):
        cu, h, d = self.counter(self.doc(40))
        def count():
            s, r = http(cu, 'GET', '/api/q/bills?from=2000-01-01&to=2100-01-01&limit=1000', None, h)
            return len(r.get('rows') or []) if s == 200 else -1
        n0 = count()
        self.assertGreaterEqual(n0, 40)
        self.assertTrue(wait(lambda: self.cloud_doc().get('version')), 'linked')
        # Cloud-side changes make the counter merge several times (vendor message, plan change)
        for i, upd in enumerate(({'notice': {'t': 'Hello', 'lv': 1}}, {'notice': None}, {'webMax': 3})):
            self.assertEqual(http(self.base, 'POST', '/api/admin/hotel', {'code': self.code, 'update': upd}, ADMIN)[0], 200)
            self.settle(cu, h, 200 + i)
            time.sleep(6)
        self.assertEqual(count(), n0 + 3, 'every old bill still on the counter, plus the 3 new ones')

    def test_04_unlinked_sqlite_counter_does_not_reach_the_cloud(self):
        d = migrated(tempfile.mkdtemp(dir=self.tmp), self.doc(1))
        port = free_port()
        p = subprocess.Popen([sys.executable, 'app_main.py', '--server', '--port', str(port), '--data', d], cwd=ROOT,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={**os.environ, 'SETU_BACKUP': 'off', 'SETU_CLOUD_URL': 'http://127.0.0.1:9'})
        self.procs.append(p)
        cu = f'http://127.0.0.1:{port}'
        self.assertTrue(wait(lambda: self._up(cu), 60))
        time.sleep(3)
        self.assertEqual(self.cloud_doc().get('version'), 0, 'a counter without a link sends nothing')


if __name__ == '__main__':
    unittest.main(verbosity=2)
