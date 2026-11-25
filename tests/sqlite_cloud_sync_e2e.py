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

    def test_06_table_qr_menu_and_order_reach_the_sqlite_counter(self):
        cu, h, _ = self.counter(self.doc(1))
        self.assertTrue(wait(lambda: ((self.cloud_doc()['data'] or {}).get('menu') or [])), 'menu in the cloud')
        sync = {'X-Setu-Hotel': self.code, 'X-Setu-Sync': self.key, 'X-Setu-Caps': 'secure1'}
        s, j = http(self.base, 'POST', '/api/qr/table', {'table': 'T-7', 'action': 'new'}, sync)
        self.assertEqual(s, 200, j)
        tok = j['tables']['T-7']['token']
        s, menu = http(self.base, 'GET', f'/api/guest/menu?t={tok}', None, {'X-Setu-Hotel': self.code})
        self.assertEqual(s, 200, menu)
        self.assertEqual(sorted(m['name'] for m in menu['items']), ['Dal Makhani', 'Paneer Tikka'], 'the guest sees the counter menu')
        oid = 'p3qr' + os.urandom(4).hex()
        s, o = http(self.base, 'POST', '/api/guest/order', {'t': tok, 'id': oid, 'items': [{'mid': 'm2', 'qty': 2}]}, {'X-Setu-Hotel': self.code})
        self.assertEqual(s, 200, o)
        def at_counter():
            s2, q = http(cu, 'GET', '/api/q/inbound-qr?status=all', None, h)
            return [r for r in (q.get('rows') or []) if r.get('order_id') == 'g' + oid] if s2 == 200 else None
        rows = wait(at_counter, 90)
        self.assertTrue(rows, 'the guest order reached the counter review queue')
        self.assertEqual((rows[0]['items'][0]['qty'], float(rows[0]['items'][0]['price'])), (2, 220.0), 'quantity from the guest, price from the menu')

    def test_07_other_modules_reach_the_cloud_copy(self):
        # Modules the op ingestion does not take (TD-0013) travel in the document: the owner's cloud copy has them.
        # (Zomato / Swiggy and Multi-Outlet are not in this hotel's plan: the cloud keeps those out, as for JSON hotels.)
        cu, h, _ = self.counter(self.doc(1))
        self.assertTrue(wait(lambda: self.cloud_doc().get('version')), 'linked')
        vals = {
            'cash': [{'id': 'c1', 'date': '2026-11-25', 'open': 2000, 'close': 5400}],
            'att': [{'id': 'a1', 'date': '2026-11-25', 'staff': 'Ravi', 'in': '09:00', 'out': '18:00'}],
            'salarySheets': [{'id': 'ss1', 'month': '2026-10', 'rows': [{'name': 'Ravi', 'net': 12000}]}],
            'reservations': [{'id': 'r1', 'date': '2026-11-30', 'time': '20:00', 'name': 'Sharma', 'pax': 6, 'table': 'T-4'}],
            'custList': [{'id': 'cu1', 'name': 'Meena', 'phone': '9876500077'}],
        }
        s, db = http(cu, 'GET', '/api/db', None, h)
        self.assertEqual(s, 200, db)
        s, r = http(cu, 'POST', '/api/ops', {'bv': db['version'], 'ops': [{'k': k, 'set': v} for k, v in vals.items()]}, h)
        self.assertEqual(s, 200, r)
        def arrived():
            d = self.cloud_doc()['data'] or {}
            return all(d.get(k) == v for k, v in vals.items())
        self.assertTrue(wait(arrived, 90), {k: (self.cloud_doc()['data'] or {}).get(k) for k in vals})

    def owner_db(self):
        s, j = http(self.base, 'GET', '/api/db', None, self.owner)
        self.assertEqual(s, 200, j)
        return j

    def test_08_owner_app_sees_the_counter_bills(self):
        cu, h, _ = self.counter(self.doc(2))
        self.assertTrue(wait(lambda: self.cloud_doc().get('version')), 'linked')
        ids = [self.settle(cu, h, 300 + i)['bill']['id'] for i in range(4)]
        self.assertTrue(wait(lambda: set(ids) <= {b['id'] for b in self.owner_db()['data'].get('bills') or []}, 90),
                        "the owner app (website) shows the counter's new bills")
        stored = self.cloud_doc()['data'].get('bills') or []
        self.assertFalse(set(ids) & {b['id'] for b in stored}, 'they are not copied into the stored document')

    def test_09_website_bill_reaches_the_counter_once(self):
        cu, h, _ = self.counter(self.doc(2))
        self.assertTrue(wait(lambda: self.cloud_doc().get('version')), 'linked')
        self.settle(cu, h, 400)
        self.assertTrue(wait(lambda: any(b['id'] == f'p3-{self.code}-400' for b in self.owner_db()['data'].get('bills') or []), 90))
        cur = self.owner_db()
        web = {'id': 'web-' + os.urandom(4).hex(), 'no': 999, 'table': '', 'channel': 'Takeaway', 'mode': 'Cash', 'date': time.strftime('%Y-%m-%d'),
               'time': '13:00', 'items': [{'mid': 'm2', 'name': 'Dal Makhani', 'price': 200, 'qty': 1}], 'sub': 200, 'tax': 10, 'total': 210, 'used': []}
        data = cur['data']
        data['bills'] = (data.get('bills') or []) + [web]
        s, r = http(self.base, 'POST', '/api/db', {'baseVersion': cur['version'], 'data': data}, self.owner)
        self.assertEqual(s, 200, r)
        stored = self.cloud_doc()['data'].get('bills') or []
        self.assertEqual([b['id'] for b in stored if b['id'] == web['id']], [web['id']], 'the website bill is stored')
        self.assertNotIn(f'p3-{self.code}-400', {b['id'] for b in stored}, "the counter's bill is not stored again from the website save")
        def on_counter():
            s2, q = http(cu, 'GET', '/api/q/bills?from=2000-01-01&to=2100-01-01&limit=1000', None, h)
            return [b for b in q.get('rows') or [] if b.get('id') == web['id']] if s2 == 200 else None
        rows = wait(on_counter, 90)
        self.assertEqual(len(rows or []), 1, 'the website bill is on the counter once')
        time.sleep(8)                                                  # more sync rounds: still once
        self.assertEqual(len(on_counter()), 1)
        mine = [b for b in self.owner_db()['data']['bills'] if b['id'] == web['id']]
        self.assertEqual(len(mine), 1, 'the owner app shows it once')

    def test_10_restore_onto_a_new_sqlite_pc_brings_every_bill(self):
        # The cloud holds JSON-time bills (stored document) and the SQLite counter's bills (sync tables)
        old = self.doc(0)
        old['bills'] = [{'id': f'jt-{i}', 'no': i + 1, 'date': '2026-01-05', 'time': '10:00', 'total': 210, 'sub': 200, 'tax': 10, 'mode': 'Cash',
                         'items': [{'mid': 'm2', 'name': 'Dal Makhani', 'price': 200, 'qty': 1}], 'used': []} for i in range(3)]
        self.assertEqual(http(self.base, 'POST', '/api/db', {'baseVersion': 0, 'data': old}, {'X-Setu-Hotel': self.code, 'X-Setu-Sync': self.key, 'X-Setu-Caps': 'secure1'})[0], 200)
        mine = self.doc(2)
        mine['auth']['password'] = 'Loop@Test2026x'          # the owner password on the counter (hashed by the program)
        cu, h, d1 = self.counter(mine)
        new = [self.settle(cu, h, 500 + i)['bill']['id'] for i in range(6)]
        s, r = http(cu, 'POST', '/api/bill/cancel', {'billId': new[0], 'idemKey': 'cx-' + new[0]}, h)
        self.assertEqual(s, 200, r)
        self.assertTrue(wait(lambda: self.sales()['bill_count'] >= 5 and self.sales()['cancelled_bill_count'] >= 1, 90), f'counter bills in the cloud {self.sales()}')
        # A new PC (empty SQLite folder) restores with the Hotel Code and the owner password
        d2 = tempfile.mkdtemp(dir=self.tmp)
        tok = 'p3-new-' + os.urandom(4).hex()
        with open(os.path.join(d2, 'setu-devices.json'), 'w', encoding='utf-8') as f:
            json.dump({tok: 'admin'}, f)
        port = free_port()
        p = subprocess.Popen([sys.executable, 'app_main.py', '--server', '--port', str(port), '--data', d2], cwd=ROOT, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, env={**os.environ, 'SETU_BACKUP': 'off', 'SETU_CLOUD_URL': self.base, 'SETU_STORAGE': 'sqlite'})
        self.procs.append(p)
        self.dirs = getattr(self, 'dirs', []) + [d2]
        cu2 = f'http://127.0.0.1:{port}'
        self.assertTrue(wait(lambda: self._up(cu2), 60))
        launch = {'X-Setu-Launch': open(os.path.join(d2, 'setu-launch.key')).read().strip()}
        s, r = http(cu2, 'POST', '/api/cloud/restore', {'hotel': self.code, 'password': 'Loop@Test2026x'}, launch)
        self.assertEqual(s, 200, r)
        def bills2():
            s2, q = http(cu2, 'GET', '/api/q/bills?from=2000-01-01&to=2100-01-01&limit=1000', None, {**launch, 'X-Setu-Token': tok})
            return q.get('rows') if s2 == 200 else None
        want = {f'jt-{i}' for i in range(3)} | set(new)
        got = wait(lambda: (lambda rows: rows if rows and want <= {b['id'] for b in rows} else None)(bills2()), 120)
        self.assertTrue(got, f'every bill restored (have {sorted(b["id"] for b in (bills2() or []))})')
        self.assertTrue(next(b for b in got if b['id'] == new[0]).get('cancelled'), 'a cancelled bill comes back cancelled')
        ids = [b['id'] for b in got]
        self.assertEqual(len(ids), len(set(ids)), 'no bill twice')

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
