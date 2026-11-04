"""Phase 2b: incremental saves on SQLite (POST /api/ops), change feed, bill window, history totals, memory.

Synthetic data only, temporary folders.

    python3 tests/sqlite_phase2b_test.py
"""
import copy
import gzip
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import warnings
warnings.simplefilter('ignore', ResourceWarning)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import setu_sqlite as S          # noqa: E402
import setu_migrate as M         # noqa: E402
import app_main as A             # noqa: E402
from sqlite_phase2_test import sample_doc   # noqa: E402


def migrated(tmp, doc):
    d = os.path.join(tmp, 'hotel')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'setu-db.json'), 'w', encoding='utf-8') as f:
        json.dump({'version': 1, 'savedAt': 1, 'data': doc}, f, ensure_ascii=False)
    r = M.migrate(d, cutover=True)
    assert r['status'] == 'MIGRATED', r
    return d


def apply_like_client(doc, ops):
    """What a device's copy looks like after its own ops (the reference the database must equal)."""
    doc = copy.deepcopy(doc)
    for op in ops:
        k = op['k']
        if 'set' in op:
            doc[k] = copy.deepcopy(op['set'])
        if 'up' in op or 'rm' in op:
            lst = doc.setdefault(k, [])
            for x in op.get('up') or []:
                i = next((i for i, y in enumerate(lst) if y.get('id') == x['id']), None)
                if i is None:
                    lst.append(copy.deepcopy(x))
                else:
                    lst[i] = copy.deepcopy(x)
            gone = set(op.get('rm') or [])
            doc[k] = [y for y in lst if y.get('id') not in gone]
        if 'mset' in op or 'mdel' in op:
            m = doc.setdefault(k, {})
            m.update(copy.deepcopy(op.get('mset') or {}))
            for mk in op.get('mdel') or []:
                m.pop(mk, None)
    return doc


class OpsEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='setu-p2b-')
        self.doc = sample_doc(40)
        self.dir = migrated(self.tmp, self.doc)
        self.store = A.SqliteSetuStore(self.dir)
        # The first save adds the credential "is set" flags to settings / auth (same as the whole-data save did)
        self.ops([{'k': 'settings', 'set': self.store._ws['settings']}])
        self.doc = self.stored()

    def tearDown(self):
        self.store.sdb.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stored(self):
        return self.store.sdb.export_document()

    def reopen(self):
        self.store.sdb.close()
        self.store = A.SqliteSetuStore(self.dir)
        return self.store

    def ops(self, ops, role='local', elev=False, bv=None, opid=None):
        body = {'ops': ops, 'bv': self.store.version if bv is None else bv}
        if opid:
            body['id'] = opid
        with self.store.lock:
            return self.store.apply_ops(body, role, elev)

    # ---- the server keeps no bill history in memory ----
    def test_memory_has_no_bills_and_window_comes_from_tables(self):
        self.assertNotIn('bills', self.store._ws)
        self.assertNotIn('"bills"', self.store.raw)
        frm = '2026-01-20'
        body = json.loads(self.store.db_payload(frm))
        want = [b for b in self.doc['bills'] if b.get('date', '') >= frm]
        self.assertEqual(S.canonical(body['data']['bills']), S.canonical(want))
        self.assertEqual(body['meta']['engine'], 'sqlite')
        self.assertEqual(body['meta']['win']['from'], frm)
        self.assertNotIn('secure', body['data'])

    # ---- every kind of save writes exactly what the device has, and survives a restart ----
    def test_record_map_and_value_ops_persist_exactly(self):
        base = self.stored()
        new_bill = {'id': 'nb1', 'no': 41, 'kot': 41, 'date': '2026-01-28', 'time': '13:00', 'table': 'T-2', 'channel': 'Dine-In', 'mode': 'UPI',
                    'items': [{'mid': 'm1', 'name': 'Dish 1 पनीर', 'price': 290.0, 'qty': 1}], 'sub': 290, 'tax': 14.5, 'total': 304.5,
                    'idemKey': 'idem_nb1', 'mv': 1, 'used': [{'sid': 'stk1', 'qty': 0.25}], 'paymentStatus': 'recorded', 'upiVerified': False}
        kot = {'id': 'k2', 'no': 2, 'date': '2026-01-28', 'items': [{'mid': 'm1', 'name': 'x', 'qty': 1}], 'status': 'new'}
        ops = [
            {'k': 'bills', 'up': [new_bill]},
            {'k': 'kots', 'up': [kot, dict(base['kots'][0], status='done')], 'prev': {'k1': base['kots'][0]}},
            {'k': 'txns', 'up': [{'id': 't9', 'type': 'Expense', 'date': '2026-01-28', 'head': 'Milk', 'amount': 250.5, 'mode': 'Cash'}]},
            {'k': 'moves', 'up': [{'id': 'w9', 'sid': 'stk3', 'qty': -2, 'type': 'waste', 'date': '2026-01-28'}]},
            {'k': 'kaccha', 'mset': {'T-9': {'cart': [{'mid': 'm2', 'qty': 3}]}}, 'mdel': ['T-3']},
            {'k': 'att', 'mset': {'2026-01-28': {'s1': 'P'}}},
            {'k': 'salarySheets', 'mset': {'2026-02': {'rows': []}}},
            {'k': 'supAlias', 'mset': {'gupta ji': 'gupta traders'}},
            {'k': 'waMessages', 'up': [{'id': 'w2', 'status': 'QUEUED'}], 'rm': ['w1']},
            {'k': 'seq', 'set': dict(base['seq'], bill=41, kot=41)},
            {'k': 'settings', 'set': dict(base['settings'], name='Synthetic Café 2')},
        ]
        code, res = self.ops(ops)
        self.assertEqual(code, 200, res)
        want = apply_like_client(base, ops)
        self.assertEqual(S.canonical(self.stored()), S.canonical(want))
        self.reopen()
        self.assertEqual(S.canonical(self.stored()), S.canonical(want), 'not the same after a restart')
        self.assertEqual(S.canonical({k: v for k, v in want.items() if k != 'bills'}), S.canonical(self.store._ws))
        # The ledger follows: one sale movement for the new bill, the waste movement, balances by trigger
        con = self.store.sdb.con()
        self.assertEqual(con.execute("SELECT COUNT(*) FROM stock_movements WHERE ref = 'nb1'").fetchone()[0], 1)
        self.assertEqual(con.execute("SELECT qty FROM stock_movements WHERE id = 'm-w9'").fetchone()[0], -2)
        self.assertEqual(con.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_prefix_ids_and_keys_do_not_touch_neighbours(self):
        # The boundary: ids / keys that are prefixes of each other (b1, b10, b100; T-5, T-50; "5", "50")
        bills = [{'id': i, 'no': 100 + n, 'date': '2026-01-27', 'total': 10 * (n + 1), 'mode': 'Cash', 'items': [], 'idemKey': 'i-' + i}
                 for n, i in enumerate(['p1', 'p10', 'p100'])]
        code, res = self.ops([{'k': 'bills', 'up': bills}, {'k': 'kaccha', 'mset': {'T-5': {'n': 5}, 'T-50': {'n': 50}}},
                              {'k': 'supAlias', 'mset': {'5': 'five', '50': 'fifty'}}, {'k': 'seq', 'set': dict(self.store._ws['seq'], bill=102)}])
        self.assertEqual(code, 200, res)
        base = self.stored()
        p10 = dict(next(b for b in base['bills'] if b['id'] == 'p10'), note='edited')
        code, res = self.ops([{'k': 'bills', 'up': [p10], 'prev': {'p10': next(b for b in base['bills'] if b['id'] == 'p10')}},
                              {'k': 'kaccha', 'mdel': ['T-5']}, {'k': 'supAlias', 'mset': {'50': 'FIFTY'}}])
        self.assertEqual(code, 200, res)
        self.reopen()
        got = self.stored()
        by = {b['id']: b for b in got['bills']}
        first = {b['id']: b for b in base['bills']}
        self.assertEqual(by['p1'], first['p1'])
        self.assertEqual(by['p100'], first['p100'])
        self.assertEqual((by['p1']['total'], by['p100']['total']), (10, 30))
        self.assertEqual(by['p10']['note'], 'edited')
        self.assertEqual({k: v for k, v in got['kaccha'].items() if k.startswith('T-5')}, {'T-50': {'n': 50}})
        self.assertEqual(got['supAlias'].get('5'), 'five')
        self.assertEqual(got['supAlias'].get('50'), 'FIFTY')
        # The change log names exactly the records touched by the second save
        rows = set(self.store.changes(self.store.version - 1)['ops'][i]['k'] for i in range(3))
        self.assertEqual(rows, {'bills', 'kaccha', 'supAlias'})
        ch = {o['k']: o for o in self.store.changes(self.store.version - 1)['ops']}
        self.assertEqual([b['id'] for b in ch['bills']['up']], ['p10'])
        self.assertEqual(ch['kaccha'], {'k': 'kaccha', 'mset': {}, 'mdel': ['T-5']})
        self.assertEqual(ch['supAlias']['mset'], {'50': 'FIFTY'})

    # ---- security: the same rules as the whole-document save ----
    def test_cashier_cannot_overwrite_confirmed_bill_or_settings(self):
        base = self.stored()
        b0 = next(b for b in base['bills'] if b['id'] == 'b0')
        tampered = dict(b0, total=1, mode='Card', items=[])
        code, res = self.ops([{'k': 'bills', 'up': [tampered], 'prev': {'b0': b0}},
                              {'k': 'settings', 'set': dict(base['settings'], name='Hacked', gst=0)},
                              {'k': 'bills', 'rm': ['b1']}], role='cashier')
        self.assertEqual(code, 200, res)
        got = {b['id']: b for b in self.stored()['bills']}
        for f in A.SEC.BILL_LOCKED:
            self.assertEqual(got['b0'].get(f), b0.get(f), f'a cashier changed {f} of a confirmed bill')
        self.assertIn('b1', got, 'a cashier deleted a bill')
        self.assertEqual(self.stored()['settings'], base['settings'])
        self.assertTrue(res.get('blocked'))
        fixed = {o['k']: o for o in res['fix']}
        self.assertEqual(next(x for x in fixed['bills']['up'] if x['id'] == 'b0'), got['b0'])
        self.assertIn('b1', [x['id'] for x in fixed['bills']['up']])

    def test_manager_cancel_and_delete_rules(self):
        base = self.stored()
        b2 = next(b for b in base['bills'] if b['id'] == 'b2')
        code, res = self.ops([{'k': 'bills', 'up': [dict(b2, cancelled=True, cancelledBy='Owner')], 'prev': {'b2': b2}}], role='cashier', elev=True)
        self.assertEqual(code, 200, res)
        got = {b['id']: b for b in self.stored()['bills']}
        self.assertTrue(got['b2']['cancelled'])
        con = self.store.sdb.con()
        self.assertEqual(con.execute("SELECT COUNT(*) FROM stock_movements WHERE ref = 'b2' AND source = 'cancel'").fetchone()[0], 1)
        self.assertEqual(con.execute("SELECT action FROM bill_modifications WHERE bill_id = 'b2'").fetchone()[0], 'cancel')
        # A cancelled bill cannot be un-cancelled, even by the main counter
        code, res = self.ops([{'k': 'bills', 'up': [dict(got['b2'], cancelled=False)], 'prev': {'b2': got['b2']}}])
        self.assertTrue({b['id']: b for b in self.stored()['bills']}['b2']['cancelled'])
        # Deleting needs the main counter / a manager: then it is logged with the old record
        code, res = self.ops([{'k': 'bills', 'rm': ['b3']}], role='local')
        self.assertNotIn('b3', {b['id'] for b in self.stored()['bills']})
        self.assertEqual(con.execute("SELECT action FROM bill_modifications WHERE bill_id = 'b3'").fetchone()[0], 'delete')

    def test_plain_pins_become_hashes_and_never_reach_devices(self):
        base = self.stored()
        staff = base['staff'] + [{'id': 's2', 'name': 'Asha', 'role': 'Cashier', 'access': 'cashier', 'pin': '4826'}]
        code, res = self.ops([{'k': 'staff', 'set': staff}])
        self.assertEqual(code, 200, res)
        sec = self.store._ws['secure']
        self.assertTrue(any(v for v in sec.get('staff', {}).values()), 'PIN not hashed')
        self.assertNotIn('4826', json.dumps(self.stored()))
        self.assertNotIn('4826', self.store.db_payload().decode())
        self.assertEqual(A.SEC.check_pin(self.store._ws, '4826')[0] if A.SEC.check_pin(self.store._ws, '4826') else None, 'cashier')
        # An unrelated save never removes the staff PIN hashes
        self.ops([{'k': 'txns', 'up': [{'id': 'tx', 'type': 'Expense', 'date': '2026-01-28', 'head': 'Tea', 'amount': 20, 'mode': 'Cash'}]}])
        self.assertTrue(A.SEC.check_pin(self.store._ws, '4826'))
        code, res = self.ops([{'k': 'staff', 'up': staff}])
        self.assertEqual(code, 400, 'staff must be saved as a whole list')

    # ---- numbers, duplicates, merges ----
    def test_number_clash_renumbered_and_duplicate_sale_refused(self):
        a = {'id': 'x1', 'no': 41, 'date': '2026-01-28', 'total': 100, 'mode': 'Cash', 'items': [], 'idemKey': 'dev-a-1'}
        b = {'id': 'x2', 'no': 41, 'date': '2026-01-28', 'total': 200, 'mode': 'Cash', 'items': [], 'idemKey': 'dev-b-1'}
        bv = self.store.version
        self.assertEqual(self.ops([{'k': 'bills', 'up': [a]}, {'k': 'seq', 'set': dict(self.store._ws['seq'], bill=41)}], bv=bv)[0], 200)
        code, res = self.ops([{'k': 'bills', 'up': [b]}, {'k': 'seq', 'set': dict(self.store._ws['seq'], bill=41)}], bv=bv)
        self.assertEqual(code, 200, res)
        self.assertEqual(res['renumbered'], {'x2': 42})
        got = {x['id']: x for x in self.stored()['bills']}
        self.assertEqual((got['x1']['no'], got['x2']['no']), (41, 42))
        self.assertEqual(self.store._ws['seq']['bill'], 42)
        # The same sale again under a new id (a retry from another tab): refused, the stored bill is returned
        again = dict(a, id='x3', no=43)
        code, res = self.ops([{'k': 'bills', 'up': [again]}])
        self.assertNotIn('x3', got)
        self.assertEqual(res['dup']['x3']['id'], 'x1')
        nos = [x['no'] for x in self.stored()['bills'] if not x.get('imported')]
        self.assertEqual(len(nos), len(set(nos)))

    def test_two_devices_edit_different_fields_of_one_record(self):
        base = self.stored()
        k1 = base['kots'][0]
        bv = self.store.version
        self.assertEqual(self.ops([{'k': 'kots', 'up': [dict(k1, status='cooking')], 'prev': {'k1': k1}}], bv=bv)[0], 200)
        code, res = self.ops([{'k': 'kots', 'up': [dict(k1, note='no onion')], 'prev': {'k1': k1}}], bv=bv)
        self.assertEqual(code, 200, res)
        got = self.stored()['kots'][0]
        self.assertEqual((got['status'], got['note']), ('cooking', 'no onion'), 'one device lost its change')
        # A removal of a record the other device changed meanwhile: it stays
        k = self.stored()['kots'][0]
        bv = self.store.version
        self.ops([{'k': 'kots', 'up': [dict(k, status='done')], 'prev': {'k1': k}}], bv=bv)
        self.ops([{'k': 'kots', 'rm': ['k1'], 'prev': {'k1': k}}], bv=bv)
        self.assertEqual([x['id'] for x in self.stored()['kots']], ['k1'])

    def test_repeated_save_applied_once(self):
        stock = self.stored()['stock']
        it = dict(stock[2], qty=stock[2]['qty'] - 5)
        r1 = self.ops([{'k': 'stock', 'up': [it]}], opid='op-1')
        v = self.store.version
        r2 = self.ops([{'k': 'stock', 'up': [it]}], opid='op-1')
        self.assertEqual(r2[1].get('repeat'), True)
        self.assertEqual(self.store.version, v)
        self.assertEqual(r1[1]['version'], r2[1]['version'])

    def test_native_settle_and_cancel_on_tables(self):
        code, r = self.store.settle_bill({'idemKey': 'n-1', 'bill': {'table': 'T-3', 'channel': 'Dine-In', 'mode': 'Cash', 'items': [{'mid': 'm1', 'name': 'x', 'price': 100, 'qty': 1}],
                                                                       'total': 105, 'date': '2026-01-28', 'used': [{'sid': 'stk1', 'qty': 0.25}], 'mv': 1}})
        self.assertEqual(code, 200, r)
        self.assertEqual(r['bill']['no'], 41)
        self.assertNotIn('T-3', self.store._ws['kaccha'], 'running order not cleared')
        code, r2 = self.store.settle_bill({'idemKey': 'n-1', 'bill': {'table': 'T-3', 'mode': 'Cash', 'total': 105}})
        self.assertTrue(r2['alreadySettled'])
        code, c = self.store.cancel_bill({'billId': r['bill']['id'], 'idemKey': 'c-1'})
        self.assertEqual(code, 200, c)
        b = next(x for x in self.stored()['bills'] if x['id'] == r['bill']['id'])
        self.assertTrue(b['cancelled'])
        self.assertEqual(self.store._ws['audit'][-1]['action'], 'Bill Cancel')
        self.assertEqual(self.store.cancel_bill({'billId': r['bill']['id'], 'idemKey': 'c-1'})[1].get('alreadyDone'), True)

    # ---- history totals (what the app derives from every bill) ----
    def client_totals(self, bills):
        """Python copy of the app's customers() / ptsBal() / walletBal() / stockMoves() over a list of bills."""
        stock, cust = {}, {}
        for b in bills:
            if b.get('mv'):
                for u in b.get('used') or []:
                    q = float(u.get('qty') or 0)
                    stock[str(u['sid'])] = stock.get(str(u['sid']), 0) - q + (q if b.get('cancelled') else 0)
            if b.get('cancelled'):
                continue
            p = S.norm_ph(b.get('phone'))
            if len(p) != 10:
                continue
            e = cust.setdefault(p, {'visits': 0, 'spend': 0, 'pts': 0, 'pa': 0, 'ws': 0, 'name': '', 'first': '', 'last': '', 'fav': {}})
            pts = S.jsnum(b.get('ptsEarned')) - S.jsnum(b.get('ptsUsed'))
            e['pa'] += pts
            if b.get('mode') == 'Wallet':
                e['ws'] += S.jsnum(b.get('total'))
            if b.get('channel') in ('Zomato', 'Swiggy'):
                continue
            if b.get('cust'):
                e['name'] = b['cust']
            if not e['visits']:
                e['first'] = b.get('date')
            e['visits'] += 1
            e['spend'] += S.jsnum(b.get('total'))
            e['last'] = b.get('date')
            e['pts'] += pts
            for it in b.get('items') or []:
                if it.get('name'):
                    e['fav'][it['name']] = e['fav'].get(it['name'], 0) + (S.jsnum(it.get('qty')) or 1)
        return stock, cust

    def test_history_totals_match_app_rules_and_follow_edits(self):
        frm = '2026-01-15'
        h = self.store.hist(frm)
        old = [b for b in self.stored()['bills'] if b.get('date', '') < frm]
        stock, cust = self.client_totals(old)
        self.assertEqual(h['bills'], len(old))
        self.assertEqual({k: round(v, 6) for k, v in h['stock'].items()}, {k: round(v, 6) for k, v in stock.items()})
        self.assertEqual(S.canonical(h['cust']), S.canonical(cust))
        # Cancel an old bill: the kept totals change exactly like a fresh count
        b = next(x for x in old if not x.get('cancelled') and x.get('mv'))
        self.ops([{'k': 'bills', 'up': [dict(b, cancelled=True, cancelledBy='Owner')], 'prev': {b['id']: b}}])
        kept = copy.deepcopy(self.store.hist(frm))
        fresh = self.store.sdb.history_totals(frm)
        self.assertEqual({k: round(v, 6) for k, v in kept['stock'].items()}, {k: round(v, 6) for k, v in fresh['stock'].items()})
        self.assertEqual(S.canonical(kept['cust']), S.canonical(fresh['cust']))

    # ---- whole-data exports stay complete without holding history in memory ----
    def test_streamed_full_export_equals_database(self):
        buf = io.StringIO()
        self.store.write_full_json(buf)
        self.assertEqual(S.canonical(json.loads(buf.getvalue())['data']), S.canonical(self.stored()))
        pub = io.StringIO()
        self.store.write_full_json(pub, public=True)
        self.assertNotIn('"secure"', pub.getvalue())
        ab = A.AutoBackup(self.store)
        ab.cfg['folder'] = os.path.join(self.tmp, 'ab')
        name = ab.run('test')
        with gzip.open(os.path.join(self.tmp, 'ab', name), 'rt', encoding='utf-8') as f:
            self.assertEqual(S.canonical(json.load(f)['data']), S.canonical(self.stored()))

    def test_server_side_write_never_deletes_bills(self):
        d = self.store.data()          # working data, no bills (WhatsApp / licence code does this)
        self.assertNotIn('bills', d)
        d['settings']['waCredits'] = 7
        self.store.write(d)
        self.assertEqual(len(self.stored()['bills']), len(self.doc['bills']))
        self.assertEqual(self.reopen().sdb.export_document()['settings']['waCredits'], 7)

    def test_change_feed_and_reload(self):
        v = self.store.version
        self.ops([{'k': 'txns', 'up': [{'id': 'tz', 'type': 'Receipt', 'date': '2026-01-28', 'head': 'Scrap', 'amount': 5, 'mode': 'Cash'}]}])
        ch = self.store.changes(v)
        self.assertEqual(ch['version'], v + 1)
        self.assertEqual(ch['ops'], [{'k': 'txns', 'up': [{'id': 'tz', 'type': 'Receipt', 'date': '2026-01-28', 'head': 'Scrap', 'amount': 5, 'mode': 'Cash'}], 'rm': []}])
        self.assertEqual(self.store.changes(self.store.version)['ops'], [])
        self.store.replace_all(self.stored())
        self.assertTrue(self.store.changes(v)['reload'])

    def test_bill_range_and_find(self):
        n, rows, last = self.store.sdb.bill_page('2026-01-01', '2026-01-10', -1, 7)
        want = [b for b in self.doc['bills'] if '2026-01-01' <= b.get('date', '') <= '2026-01-10']
        self.assertEqual(n, len(want))
        got = rows
        while len(rows) == 7:
            _, rows, last = self.store.sdb.bill_page('2026-01-01', '2026-01-10', last, 7)
            got += rows
        self.assertEqual(S.canonical(got), S.canonical(want))
        r = self.store.query('bill-find', {'q': '5'})
        self.assertEqual([b['no'] for b in r['rows']], [5])


if __name__ == '__main__':
    unittest.main(verbosity=2)
