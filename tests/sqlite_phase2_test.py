"""Phase 2 SQLite storage: unit and integration tests (synthetic data only, temporary folders).

    python3 tests/sqlite_phase2_test.py            (or: python3 -m unittest tests/sqlite_phase2_test.py)
"""
import copy
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import warnings
warnings.simplefilter('ignore', ResourceWarning)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
import setu_sqlite as S          # noqa: E402
import setu_migrate as M         # noqa: E402


def sample_doc(nbills=50):
    """A hotel with every shape the app stores, including the awkward ones."""
    stock = [{'id': f'stk{i}', 'name': f'Item {i}', 'unit': 'kg', 'qty': 100.0 if i else 100, 'rate': 42.5, 'cat': 'Dry'} for i in range(5)]
    menu = [{'id': f'm{i}', 'name': f'Dish {i} पनीर', 'cat': 'Main', 'price': 290.0 if i == 1 else 120, 'veg': True,
             'recipe': [{'sid': f'stk{i % 5}', 'qty': 0.25}]} for i in range(4)]
    menu.append({'id': 'mNoRecipe', 'name': 'Water', 'price': 20})          # no recipe key at all
    bills = []
    for i in range(nbills):
        b = {'id': f'b{i}', 'no': i + 1, 'kot': i + 1, 'date': '2026-01-%02d' % (1 + i % 28), 'time': '12:%02d' % (i % 60), 'table': f'T-{1 + i % 4}',
             'channel': 'Dine-In', 'mode': ['Cash', 'UPI', 'Card'][i % 3], 'items': [{'mid': 'm1', 'name': 'Dish 1 पनीर', 'price': 290.0, 'qty': 2}],
             'sub': 580, 'disc': 0, 'tax': 29.0, 'total': 609.005 if i == 3 else 609, 'idemKey': f'idem_b{i}', 'mv': 1,
             'used': [{'sid': 'stk1', 'qty': 0.5}], 'phone': '98765432%02d' % (i % 7), 'ptsEarned': 6, 'note': None, 'nested': {'a': [1, {'b': False}]}}
        if i % 10 == 9:
            b.update(mode='Split', pays=[{'mode': 'Cash', 'amt': 300}, {'mode': 'UPI', 'amt': 309}])
        if i == 5:
            b.update(cancelled=True, cancelledBy='Manager')
        if i == 7:
            b['pays'] = []                                                   # empty array kept as is
        bills.append(b)
    bills.append({'id': 'imp1', 'no': 1, 'date': '2025-03-01', 'imported': 1, 'total': 50, 'mode': 'Cash'})   # imported: own number
    txns = [{'id': 't1', 'type': 'Purchase', 'date': '2026-01-02', 'time': '10:00', 'head': 'Item 1', 'party': 'Gupta Traders', 'amount': 1000.1, 'mode': 'Credit',
             'sid': 'stk1', 'qty': 20, 'mv': 1, 'inv': {'id': 'inv1', 'no': 'A-1', 'total': 1000.1, 'paid': 400, 'n': 1}},
            {'id': 't2', 'type': 'Expense', 'date': '2026-01-03', 'head': 'Supplier Payment', 'party': ' gupta traders', 'amount': 400, 'mode': 'Cash', 'inv': {'id': 'inv1'}},
            {'id': 't3', 'type': 'Expense', 'date': '2026-01-03', 'head': 'Gas', 'party': 'Gupta', 'amount': 800, 'mode': 'Credit'},
            {'id': 't4', 'type': 'Receipt', 'date': '2026-01-04', 'head': 'Scrap sale', 'amount': 120.75, 'mode': 'Cash'}]
    moves = [{'id': f'open-stk{i}', 'sid': f'stk{i}', 'qty': 100, 'type': 'open', 'date': '2026-01-01'} for i in range(5)]
    moves.append({'id': 'w1', 'sid': 'stk2', 'qty': -1.5, 'type': 'waste', 'date': '2026-01-05', 'note': 'spoiled'})
    doc = {
        'auth': {'hotelId': 'SYNTH1', 'isRegistered': True}, 'settings': {'name': 'Synthetic Café', 'hotelId': 'SYNTH1', 'gst': 5, 'tables': ['T-1', 'T-2']},
        'subscription': {'status': 'active'}, 'secure': {'admin': 'pbkdf2$x'}, 'seq': {'bill': nbills, 'kot': nbills, 'token': 3, 'tokenDate': '2026-01-28'},
        'menu': menu, 'stock': stock, 'bills': bills, 'kots': [{'id': 'k1', 'no': 1, 'date': '2026-01-28', 'items': [{'mid': 'm1', 'name': 'x', 'qty': 1}], 'status': 'new'}],
        'txns': txns, 'moves': moves, 'staff': [{'id': 's1', 'name': 'Ravi', 'role': 'Chef'}],
        'audit': [{'id': 'a1', 'at': 1, 'date': '2026-01-01', 'action': 'Login', 'user': 'Owner', 'amount': 0, 'ref': ''}],
        'att': {'2026-01-01': {'s1': 'P'}, '2026-01-02': {}}, 'cash': {'2026-01-01': {'open': 500}}, 'kaccha': {'T-3': {'cart': [{'mid': 'm1', 'qty': 1}]}},
        'custList': [{'phone': '9876543210', 'name': 'A'}],                  # no ids: generic rows
        'qrDone': ['q1', 'q2'], 'stockAlias': {}, 'supAlias': {'gupta': 'gupta traders'}, 'cnotes': [], 'orders': [],
        'salarySheets': {'2026-01': {'rows': [1, 2]}}, 'demoCleanupDone': True, 'nullKey': None, 'waMessages': [{'id': 'w1', 'status': 'SENT'}],
    }
    for i, s in enumerate(doc['stock']):
        s['qty'] = M.legacy_stock(doc).get(s['id'], s['qty'])
    return doc


def new_db(tmp, name='t.sqlite'):
    return S.SqliteDoc(os.path.join(tmp, name), create=True)


class SqlitePhase2(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='setu-p2-')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_roundtrip_is_exact(self):
        doc = sample_doc()
        db = new_db(self.tmp)
        with db.tx() as c:
            db.import_document(c, doc, 7, 123)
        self.assertEqual(S.canonical(db.export_document()), S.canonical(doc))
        self.assertEqual(list(db.export_document().keys()), list(doc.keys()))
        self.assertEqual(db.meta('hotel_id'), 'SYNTH1')
        # exact numeric types survive (290.0 stays a float, 609 stays an int)
        out = db.export_document()
        self.assertIsInstance(out['bills'][0]['items'][0]['price'], float)
        self.assertIsInstance(out['bills'][0]['total'], int)
        self.assertEqual(out['bills'][3]['total'], 609.005)

    def test_verification_passes_and_detects_tampering(self):
        doc = sample_doc()
        db = new_db(self.tmp)
        with db.tx() as c:
            db.import_document(c, doc)
        checks = M.verify(doc, db)
        self.assertTrue(all(ch['pass'] or not ch['mandatory'] for ch in checks), [ch for ch in checks if not ch['pass']])
        # a changed amount in the database must be caught
        db.con().execute("UPDATE bills SET total = 1, total_p = 100 WHERE id = 'b0'")
        failed = [ch['check'] for ch in M.verify(doc, db) if not ch['pass'] and ch['mandatory']]
        self.assertTrue(any('identical' in f for f in failed) and any('Sales total' in f for f in failed), failed)

    def test_incremental_write_touches_only_changes(self):
        doc = sample_doc(400)
        db = new_db(self.tmp)
        with db.tx() as c:
            db.import_document(c, doc)
        con = db.con()
        new = copy.deepcopy(doc)
        new['bills'].append(dict(new['bills'][0], id='bNEW', no=401, idemKey='idem_new'))
        new['bills'][10] = dict(new['bills'][10], cancelled=True)
        before = con.total_changes
        with db.tx() as c:
            db.commit_document(c, doc, new, 2, 1)
        writes = con.total_changes - before
        self.assertLess(writes, 60, f'{writes} rows written for 2 changed bills out of 401')
        self.assertEqual(S.canonical(db.export_document()), S.canonical(new))
        mods = con.execute("SELECT bill_id, action FROM bill_modifications").fetchall()
        self.assertIn(('b10', 'cancel'), mods)

    def test_stock_ledger_exactly_once(self):
        doc = sample_doc()
        db = new_db(self.tmp)
        with db.tx() as c:
            db.import_document(c, doc)
        n0 = db.con().execute('SELECT COUNT(*) FROM stock_movements').fetchone()[0]
        bal0 = db.stock_balances()
        # the same bill re-saved (e.g. an edit) twice: its movements are replaced, never added again
        for k in range(2):
            new = copy.deepcopy(doc)
            new['bills'][0]['note'] = f'edit {k}'
            with db.tx() as c:
                db.commit_document(c, doc, new, 2 + k, 1)
            doc = new
        self.assertEqual(db.con().execute('SELECT COUNT(*) FROM stock_movements').fetchone()[0], n0)
        self.assertEqual(db.stock_balances(), bal0)
        # cancel: one reversal per used line, balance restored once
        new = copy.deepcopy(doc)
        new['bills'][0]['cancelled'] = True
        with db.tx() as c:
            db.commit_document(c, doc, new, 9, 1)
        self.assertEqual(db.con().execute("SELECT COUNT(*) FROM stock_movements WHERE source = 'cancel' AND ref = 'b0'").fetchone()[0], 1)
        self.assertAlmostEqual(db.stock_balances()['stk1'], bal0['stk1'] + 0.5, places=6)
        self.assertEqual(M.legacy_stock(new)['stk1'], round(db.stock_balances()['stk1'], 3))

    def test_transaction_rolls_back_completely(self):
        doc = sample_doc()
        db = new_db(self.tmp)
        with db.tx() as c:
            db.import_document(c, doc)
        snap = S.canonical(db.export_document())
        new = copy.deepcopy(doc)
        new['bills'].append(dict(new['bills'][0], id='boom', no=999, idemKey='idem_boom'))
        orig = db._voucher_side
        new['txns'].append({'id': 'tX', 'type': 'Expense', 'amount': 5})

        def fail(*a):
            raise RuntimeError('disk full (simulated)')
        db._voucher_side = fail
        with self.assertRaises(RuntimeError):
            with db.tx() as c:
                db.commit_document(c, doc, new, 2, 1)
        db._voucher_side = orig
        self.assertEqual(S.canonical(db.export_document()), snap, 'a failed transaction must leave nothing behind')
        self.assertIsNone(db.con().execute("SELECT 1 FROM bills WHERE id = 'boom'").fetchone())

    def test_backup_restore_and_corruption_detection(self):
        doc = sample_doc(200)
        db = new_db(self.tmp)
        with db.tx() as c:
            db.import_document(c, doc)
        gz = os.path.join(self.tmp, 'setu-2026-01-28.sqlite.gz')
        info = db.backup_to(gz, 1, keep=5)
        self.assertTrue(info['verified'])
        self.assertEqual(info['bills'], 201)
        dest = os.path.join(self.tmp, 'restored.sqlite')
        r = S.restore_backup(gz, dest, expected_hotel_id='SYNTH1')
        self.assertEqual(r['integrity'], 'ok')
        self.assertEqual(S.canonical(S.SqliteDoc(dest).export_document()), S.canonical(doc))
        # damage a copy: the store refuses to open it instead of serving wrong data
        bad = os.path.join(self.tmp, 'bad.sqlite')
        shutil.copy(dest, bad)
        size = os.path.getsize(bad)
        with open(bad, 'r+b') as f:
            for off in range(4096 * 3, size - 4096, 4096 * 7):
                f.seek(off + 100)
                f.write(os.urandom(800))
        with self.assertRaises((S.StoreError, sqlite3.DatabaseError)):
            S.SqliteDoc(bad)

    def test_hotel_id_is_fixed(self):
        db = new_db(self.tmp)
        with db.tx() as c:
            db.import_document(c, sample_doc())
        db.close()
        with self.assertRaises(S.StoreError):
            S.SqliteDoc(os.path.join(self.tmp, 't.sqlite'), hotel_id='OTHER')

    def _folder(self, doc):
        d = os.path.join(self.tmp, 'hotel')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'setu-db.json'), 'w', encoding='utf-8') as f:
            json.dump({'version': 5, 'savedAt': 1, 'data': doc}, f)
        return d

    def test_migration_dry_run_cutover_rerun(self):
        d = self._folder(sample_doc())
        src = open(os.path.join(d, 'setu-db.json'), 'rb').read()
        r = M.migrate(d)
        self.assertEqual(r['status'], 'DRY_RUN_PASSED', r.get('message'))
        self.assertFalse(os.path.exists(os.path.join(d, S.DB_FILE)))
        self.assertEqual(S.read_flag(d), {})
        r = M.migrate(d, cutover=True)
        self.assertEqual(r['status'], 'MIGRATED', r.get('message'))
        self.assertEqual(S.read_flag(d)['engine'], 'sqlite')
        self.assertEqual(open(os.path.join(d, 'setu-db.json'), 'rb').read(), src, 'legacy JSON must never change')
        self.assertTrue(os.path.exists(r['safety_copy']))
        self.assertEqual(M.migrate(d, cutover=True)['status'], 'ALREADY_MIGRATED')
        out = os.path.join(self.tmp, 'export.json')
        M.export_json(d, out)
        self.assertEqual(S.canonical(json.load(open(out, encoding='utf-8'))['data']), S.canonical(sample_doc()))

    def test_migration_failure_leaves_json_in_charge(self):
        d = self._folder(sample_doc())
        orig = M.verify
        M.verify = lambda doc, db: [{'check': 'forced failure', 'pass': False, 'mandatory': True, 'expected': 1, 'actual': 2, 'note': ''}]
        try:
            r = M.migrate(d, cutover=True)
        finally:
            M.verify = orig
        self.assertEqual(r['status'], 'FAILED')
        self.assertEqual(S.read_flag(d), {})
        self.assertFalse(os.path.exists(os.path.join(d, S.DB_FILE)))
        self.assertTrue(os.path.exists(os.path.join(d, 'migration', 'migration-report.md')))

    def test_migration_killed_midway_then_restarted(self):
        doc = sample_doc(3000)
        d = self._folder(doc)
        code = ('import sys, setu_migrate as M, setu_sqlite as S\n'
                'orig = S.SqliteDoc._put_record\n'
                'n = [0]\n'
                'def slow(self, *a):\n'
                '    n[0] += 1\n'
                '    if n[0] == 1500:\n'
                '        import os; os._exit(9)   # power cut in the middle of the import\n'
                '    return orig(self, *a)\n'
                'S.SqliteDoc._put_record = slow\n'
                f'M.migrate({d!r}, cutover=True)\n')
        p = subprocess.run([sys.executable, '-c', code], cwd=ROOT)
        self.assertEqual(p.returncode, 9)
        self.assertEqual(S.read_flag(d), {}, 'no switch after an interrupted migration')
        self.assertTrue(os.path.exists(os.path.join(d, S.DB_FILE + '.migrating')))
        r = M.migrate(d, cutover=True)
        self.assertEqual(r['status'], 'MIGRATED', r.get('message'))
        self.assertEqual(S.canonical(S.SqliteDoc(os.path.join(d, S.DB_FILE)).export_document()), S.canonical(doc))


class CounterServerOnSqlite(unittest.TestCase):
    """The real counter server (app_main.py) on a migrated synthetic folder."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='setu-p2-srv-')
        doc = sample_doc(500)
        doc['settings']['adminPin'] = '739146'
        with open(os.path.join(cls.tmp, 'setu-db.json'), 'w', encoding='utf-8') as f:
            json.dump({'version': 3, 'savedAt': 1, 'data': doc}, f)
        assert M.migrate(cls.tmp, cutover=True)['status'] == 'MIGRATED'
        cls.port = 8650
        cls.start()

    @classmethod
    def start(cls):
        cls.proc = subprocess.Popen([sys.executable, os.path.join(ROOT, 'app_main.py'), '--server', '--port', str(cls.port), '--data', cls.tmp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import urllib.request
        for _ in range(100):
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{cls.port}/api/ping', timeout=1)
                break
            except Exception:
                time.sleep(0.15)
        cls.launch = open(os.path.join(cls.tmp, 'setu-launch.key')).read().strip()
        cls.tok = cls.call('/api/login', {'pin': '739146'}, tok=None)[1]['token']

    @classmethod
    def call(cls, path, body=None, tok='self'):
        import urllib.request
        import urllib.error
        h = {'Content-Type': 'application/json', 'X-Setu-Launch': cls.launch}
        if tok:
            h['X-Setu-Token'] = cls.tok if tok == 'self' else tok
        req = urllib.request.Request(f'http://127.0.0.1:{cls.port}{path}', data=json.dumps(body).encode() if body is not None else None, headers=h, method='POST' if body is not None else 'GET')
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}')

    @classmethod
    def tearDownClass(cls):
        cls.proc.kill()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def bill(self, i):
        return {'id': f'srv-{i}', 'table': '', 'channel': 'Takeaway', 'mode': 'Cash', 'items': [{'mid': 'm1', 'name': 'x', 'price': 100, 'qty': 1}],
                'sub': 100, 'tax': 5, 'total': 105, 'date': '2026-01-28', 'time': '13:00', 'used': []}

    def test_concurrent_settles_unique_numbers_no_duplicates(self):
        res = []

        def go(i):
            res.append(self.call('/api/bill/settle', {'idemKey': f'c-{i % 40}', 'bill': self.bill(i % 40)}))
        ts = [threading.Thread(target=go, args=(i,)) for i in range(100)]   # 100 requests, 40 distinct bills
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertTrue(all(s == 200 for s, _ in res), [s for s, _ in res if s != 200])
        db = self.call('/api/db?from=2000-01-01')[1]['data']
        mine = [b for b in db['bills'] if str(b.get('idemKey')).startswith('c-')]
        self.assertEqual(len(mine), 40)
        nos = [b['no'] for b in db['bills'] if not b.get('imported')]
        self.assertEqual(len(nos), len(set(nos)), 'a bill number was given twice')

    def test_kill_9_during_settles_keeps_every_acknowledged_bill(self):
        acked, stop = [], threading.Event()

        def worker(w):
            i = 0
            while not stop.is_set():
                key = f'k9-{w}-{i}'
                try:
                    s, j = self.call('/api/bill/settle', {'idemKey': key, 'bill': self.bill(f'{w}-{i}')})
                    if s == 200:
                        acked.append(key)
                except Exception:
                    pass
                i += 1
        ts = [threading.Thread(target=worker, args=(w,)) for w in range(8)]
        [t.start() for t in ts]
        time.sleep(3)
        self.proc.kill()                      # power cut: no shutdown, no flush
        self.proc.wait()
        stop.set()
        [t.join() for t in ts]
        self.__class__.start()
        db = self.call('/api/db?from=2000-01-01')[1]['data']
        have = {b.get('idemKey') for b in db['bills']}
        lost = [k for k in acked if k not in have]
        self.assertGreater(len(acked), 10)
        self.assertEqual(lost, [], f'{len(lost)} acknowledged bills lost after kill -9')
        con = sqlite3.connect(os.path.join(self.tmp, S.DB_FILE))
        self.assertEqual(con.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        orphans = con.execute("SELECT COUNT(*) FROM bills b WHERE b.arrays LIKE '%items%' AND NOT EXISTS (SELECT 1 FROM bill_items i WHERE i.bill_id = b.id)").fetchone()[0]
        self.assertEqual(orphans, 0, 'a bill without its items (half-written transaction)')

    def test_expired_subscription_refused_after_restart(self):
        # Same check as gate1_gate2 TC-SEC05, through a normal save instead of editing the old JSON file by hand
        s, db = self.call('/api/db')
        d = db['data']
        auth = dict(d.get('auth') or {}, hotelId='SYNTH1', paidUntil=int(time.time() * 1000) - 86400000)
        s, r = self.call('/api/ops', {'bv': db['version'], 'ops': [{'k': 'auth', 'set': auth}]})
        self.assertEqual(s, 200, r)
        self.proc.kill(); self.proc.wait()
        self.__class__.start()
        s, r = self.call('/api/hotel/auth', {'hotelId': 'SYNTH1', 'password': '739146'}, tok=None)
        self.assertEqual(s, 402, r)
        s, db = self.call('/api/db')
        d = db['data']
        d['auth']['paidUntil'] = int(time.time() * 1000) + 86400000 * 365
        self.assertEqual(self.call('/api/ops', {'bv': db['version'], 'ops': [{'k': 'auth', 'set': d['auth']}]})[0], 200)

    def test_queries_and_status(self):
        s, r = self.call('/api/q/bills?from=2026-01-01&to=2026-01-31&limit=5')
        self.assertEqual(s, 200)
        self.assertEqual(len(r['rows']), 5)
        s, r = self.call('/api/q/status')
        self.assertEqual(r['engine'], 'sqlite')
        self.assertIn('Phase 3', r['cloudSync'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
