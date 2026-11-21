"""Phase 3.5e: credit-note cloud sync and owner-report parity over real HTTP (local Worker in Miniflare + real SQLite counter).

Synthetic hotels and data only; temporary Worker state; never a production URL.

    python tests/phase35e_credit_note_e2e.py        # needs cloud/node_modules (npm ci in cloud/)
"""
import hashlib
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phase35d_local_e2e import A, S, DEAD, WRANGLER, LoopbackBase, http, migrated, sample_doc  # noqa: E402


def r2(x):
    return round(x + 1e-9, 2)


@unittest.skipUnless(os.path.exists(WRANGLER), 'cloud/node_modules missing: run npm ci in cloud/ (SKIPPED, not passed)')
class CreditNoteLoopback(LoopbackBase):
    def setUp(self):
        self.code, self.key = self.new_hotel('A')
        s, j = http(self.base, 'POST', '/api/login', {'pin': 'Loop@Test2026x'}, {'X-Setu-Hotel': self.code})
        self.assertEqual(s, 200, j)
        self._tok = j['token']
        d = sample_doc(3)
        d['settings']['hotelId'] = d['auth']['hotelId'] = self.code
        self.tag = os.urandom(4).hex()
        self.dir = migrated(tempfile.mkdtemp(dir=self.tmp), d)
        self.store = A.SqliteSetuStore(self.dir)
        self.disp = S.OutboxSyncDispatcher(self.store, url=self.base, hotel=self.code, key=self.key, enabled=True, batch_size=50)
        self.n = 0

    def tearDown(self):
        self.store.sdb.close()

    # ------------------------------------------------------------------ helpers
    def h(self, code=None, key=None):
        return {'X-Setu-Hotel': code or self.code, 'X-Setu-Sync': key or self.key, 'X-Setu-Caps': 'secure1'}

    def report(self, name, code=None, tok=None, **q):
        qs = '&'.join(f'{k}={v}' for k, v in q.items())
        s, j = http(self.base, 'GET', f'/api/reports/{name}' + ('?' + qs if qs else ''), None,
                    {'X-Setu-Hotel': code or self.code, 'X-Setu-Token': tok or self._tok})
        self.assertEqual(s, 200, j)
        return j

    def pending(self):
        return self.store.sdb.con().execute('SELECT COUNT(*) FROM sync_outbox WHERE sent_at IS NULL').fetchone()[0]

    def held(self):
        return dict(self.store.sdb.con().execute(
            "SELECT o.ref, c.reason FROM sync_outbox o JOIN sync_conflicts c ON c.rid = o.ref WHERE o.sent_at < 0").fetchall())

    def drain(self, rounds=10):
        for _ in range(rounds):
            r = self.disp.dispatch_once()
            if self.pending() == 0 or r.get('status') != 'ok':
                return r
        return r

    def bill(self, lines=((100, 2),), rate=5, date='2026-11-09', mode='Cash'):
        """Settles a bill on the counter (exclusive GST); returns the saved record."""
        self.n += 1
        bid = f'cb-{self.tag}-{self.n}'
        items = [{'mid': f'm{k}', 'name': f'Dish {k}', 'price': p, 'qty': q} for k, (p, q) in enumerate(lines)]
        sub = sum(p * q for p, q in lines)
        tax = r2(sub * rate / 100)
        code, r = self.store.settle_bill({'idemKey': f'idem-{bid}', 'bill': {
            'id': bid, 'table': '', 'channel': 'Takeaway', 'mode': mode, 'items': items, 'sub': sub, 'disc': 0, 'taxable': sub,
            'gstRate': rate, 'tax': tax, 'total': r2(sub + tax), 'date': date, 'time': '12:00', 'used': []}})
        self.assertEqual(code, 200, r)
        return self.store.sdb.get_records(self.store.sdb.con(), 'bills', [bid])[bid]

    def cn_doc(self, b, lines, refund='Cash', date=None):
        """A credit note exactly as the app's saveCreditNote() builds it (cnCalc, exclusive GST)."""
        self.n += 1
        items = [{'k': k, 'qty': q, 'name': b['items'][k]['name'], 'price': b['items'][k]['price'], 'mid': b['items'][k]['mid']} for k, q in lines]
        gross = sum(i['qty'] * i['price'] for i in items)
        f = (b['sub'] - (b.get('disc') or 0)) / b['sub'] if b['sub'] else 1
        net, rate = r2(gross * f), float(b.get('gstRate') or 0)
        tax = r2(net * rate / 100)
        return {'id': f'cn-{self.tag}-{self.n}', 'no': self.n, 'date': date or b['date'], 'time': '18:00', 'billId': b['id'], 'billNo': b['no'],
                'billDate': b['date'], 'cust': '', 'phone': '', 'gstin': '', 'channel': b.get('channel', 'Takeaway'), 'rate': rate, 'incl': False,
                'items': items, 'taxable': net, 'tax': tax, 'total': r2(net + tax), 'reason': 'Item returned / not served', 'refund': refund,
                'by': 'Manager', 'at': int(time.time() * 1000)}

    def save_cn(self, cn):
        """Saves a credit note (and its refund voucher) through the counter, as the app's save() does."""
        ops = [{'k': 'cnotes', 'up': [cn]}]
        if cn['refund'] != 'none':
            ops.append({'k': 'txns', 'up': [{'id': 'rf-' + cn['id'], 'type': 'Expense', 'date': cn['date'], 'time': cn['time'], 'head': 'Customer Refund',
                                             'desc': f"Credit Note CN-{cn['no']} on bill #{cn['billNo']}", 'party': '', 'amount': cn['total'],
                                             'mode': cn['refund'], 'by': 'Manager', 'cn': cn['id']}]})
        with self.store.lock:
            code, r = self.store.apply_ops({'bv': self.store.version, 'ops': ops}, 'local', True)
        self.assertEqual(code, 200, r)
        return cn

    def queue_raw(self, op_id, cns, version=None):
        """Queues an op the way a faulty or older client could send it (bypasses the app's own checks)."""
        env = S.make_sync_envelope(op_id, self.code, 'counter_test', version or self.store.version + 1000, int(time.time() * 1000),
                                   writes_rec={'cnotes': ('spec', cns, [])})
        with self.store.sdb.tx() as c:
            S.SqliteDoc.append_outbox(c, 'ops', op_id, env['doc_version'], env)
        return env

    def assert_parity(self):
        """Owner cloud sales report == counter totals, credit-note fields included (integer paise)."""
        local_b, local_c = S.local_synced_bill_totals(self.store.sdb), S.local_synced_credit_note_totals(self.store.sdb)
        cloud = self.report('sales')['summary']
        for k in ('bill_count', 'gross_sales_p', 'cancelled_bill_count', 'cancelled_amount_p'):
            self.assertEqual(cloud[k], local_b[k], k)
        for lk, ck in (('count', 'credit_note_count'), ('total_p', 'credit_note_total_p'), ('taxable_p', 'credit_note_taxable_p'),
                       ('tax_p', 'credit_note_tax_p'), ('refunded_p', 'credit_note_refunded_p'), ('adjusted_p', 'credit_note_adjusted_p'),
                       ('on_cancelled_count', 'credit_notes_on_cancelled_bills'), ('on_cancelled_p', 'credit_notes_on_cancelled_bills_p')):
            self.assertEqual(cloud[ck], local_c[lk], f'{ck}: cloud {cloud[ck]} vs counter {local_c[lk]}')
        self.assertEqual(cloud['net_sales_after_credit_notes_p'], local_b['gross_sales_p'] - local_c['total_p'])
        return cloud

    # ------------------------------------------------------------------ accounting scenarios
    def test_01_partial_multiple_full_and_over_credit(self):
        b = self.bill(((100, 2), (50, 1)))                                  # 250 + 5% = 262.50
        before = None
        self.drain()
        before = self.report('sales')['summary']
        self.save_cn(self.cn_doc(b, [(0, 1)], 'Cash'))                     # partial: 105.00
        self.save_cn(self.cn_doc(b, [(0, 1), (1, 1)], 'none'))             # rest: 157.50, adjusted
        self.queue_raw(f'over-{self.tag}', [self.cn_doc(b, [(1, 1)], 'Cash')])   # a third would exceed the bill
        self.bill()                                                          # a later bill must still sync
        self.drain()
        self.assertEqual(self.pending(), 0, 'nothing retried forever')
        self.assertEqual(self.held(), {f'over-{self.tag}': 'CREDIT_NOTE_EXCEEDS_BILL'})
        cloud = self.assert_parity()
        self.assertEqual((cloud['credit_note_count'], cloud['credit_note_total_p']), (2, 26250))
        self.assertEqual((cloud['credit_note_taxable_p'], cloud['credit_note_tax_p']), (25000, 1250))
        self.assertEqual((cloud['credit_note_refunded_p'], cloud['credit_note_adjusted_p']), (10500, 15750))
        self.assertEqual(cloud['gross_sales_p'] - before['gross_sales_p'], 21000, 'the original sale stays as it was; only the new bill added')
        gst = self.report('gst')['summary']
        self.assertEqual((gst['credit_note_gst_p'], gst['net_gst_after_credit_notes_p']), (1250, gst['total_gst_p'] - 1250))
        exp = self.report('expenses')
        self.assertEqual((exp['credit_note_refunds']['count'], exp['credit_note_refunds']['total_p']), (1, 10500))
        self.assertFalse(any(t['type'] == 'Expense' for t in exp['by_type']), 'a refund against a credit note is not an expense')

    def test_02_non_taxable_unpaid_credit_bill_and_later_period(self):
        free = self.bill(((80, 1),), rate=0)
        on_account = self.bill(((200, 1),), mode='Credit', date='2026-10-31')   # unpaid credit sale in October
        self.save_cn(self.cn_doc(free, [(0, 1)], 'UPI'))
        self.save_cn(self.cn_doc(on_account, [(0, 1)], 'none', date='2026-11-02'))   # adjusted against the dues, in November
        self.drain()
        self.assertEqual(self.held(), {})
        cloud = self.assert_parity()
        self.assertEqual(cloud['credit_note_adjusted_p'], 21000, 'credit note on an unpaid bill reduces dues, no money paid out')
        octo = self.report('sales', **{'from': '2026-10-01', 'to': '2026-10-31'})['summary']
        nov = self.report('sales', **{'from': '2026-11-01', 'to': '2026-11-30'})['summary']
        self.assertEqual((octo['bill_count'], octo['credit_note_count']), (1, 0), 'October keeps its sale unchanged')
        self.assertEqual((nov['credit_note_count'], nov['credit_note_total_p']), (2, 8000 + 21000), 'credit notes count in their own month')
        self.assertEqual(nov['credit_note_tax_p'], 1000, 'only the taxable bill carries GST back')
        reg = self.report('credit-notes')
        self.assertEqual(len(reg['credit_notes']), 2)
        self.assertTrue(all(c['bill_known'] for c in reg['credit_notes']))

    def test_03_cancel_after_credit_note_blocked_and_legacy_not_double_counted(self):
        b = self.bill()
        self.save_cn(self.cn_doc(b, [(0, 1)], 'Cash'))
        code, r = self.store.cancel_bill({'billId': b['id'], 'idemKey': 'c-' + self.tag})
        self.assertEqual(code, 409, r)
        self.assertIn('credit note', r['error'])
        # Data made before this guard: the bill was cancelled after its credit note
        with self.store.lock:
            code, r = self.store.apply_ops({'bv': self.store.version, 'ops': [{'k': 'bills', 'up': [dict(b, cancelled=True, cancelledBy='Manager')]}]},
                                           'local', True)
        self.assertEqual(code, 200, r)
        self.drain()
        cloud = self.assert_parity()
        self.assertEqual((cloud['bill_count'], cloud['cancelled_bill_count']), (0, 1))
        self.assertEqual((cloud['credit_note_count'], cloud['credit_note_total_p']), (0, 0), 'not deducted a second time')
        self.assertEqual((cloud['credit_notes_on_cancelled_bills'], cloud['credit_notes_on_cancelled_bills_p']), (1, 10500))
        self.assertEqual(cloud['net_sales_after_credit_notes_p'], 0)

    # ------------------------------------------------------------------ reconciliation & recovery
    def test_04_offline_reconnect_lost_ack_restarts_no_duplicates(self):
        b = self.bill()
        self.drain()
        self.disp.url = DEAD
        cn = self.save_cn(self.cn_doc(b, [(0, 1)], 'Cash'))
        self.assertEqual(self.disp.dispatch_once()['status'], 'network_error')
        self.assertEqual(self.pending(), 1, 'credit note kept while offline')

        def lose_reply(url, path, body, headers, timeout=15):
            S.OutboxSyncDispatcher._default_http_post(url, path, body, headers, timeout)
            raise OSError('reply lost')
        lossy = S.OutboxSyncDispatcher(self.store, url=self.base, hotel=self.code, key=self.key, enabled=True, http_post_fn=lose_reply)
        self.assertEqual(lossy.dispatch_once()['status'], 'network_error')
        self.assertEqual(self.pending(), 1)
        self.restart_worker()                                                       # Worker / Durable Object restart
        self.store.sdb.close()                                                      # counter restart
        self.store = A.SqliteSetuStore(self.dir)
        self.disp = S.OutboxSyncDispatcher(self.store, url=self.base, hotel=self.code, key=self.key, enabled=True)
        self.assertEqual(self.pending(), 1, 'survives both restarts')
        self.drain()
        self.assertEqual(self.pending(), 0)
        env = json.loads(self.store.sdb.con().execute("SELECT payload FROM sync_outbox WHERE payload LIKE ?", (f'%{cn["id"]}%',)).fetchone()[0])
        s, j = http(self.base, 'POST', '/api/sync/ops', {'batch': [env]}, self.h())          # a third delivery
        self.assertTrue(j['results'][env['op_id']].get('duplicate'), j)
        reg = self.report('credit-notes')
        self.assertEqual([c['id'] for c in reg['credit_notes']], [cn['id']], 'exactly one credit note in the cloud')
        self.assert_parity()

    def test_05_wrong_tenant_refused(self):
        b = self.bill()
        self.drain()
        code_b, key_b = self.hotels['B']
        env = S.make_sync_envelope(f'xt-{self.tag}', code_b, 'd', 5, 1, writes_rec={'cnotes': ('spec', [self.cn_doc(b, [(0, 1)])], [])})
        s, j = http(self.base, 'POST', '/api/sync/ops', {'batch': [env]}, self.h())
        self.assertEqual(j['results'][env['op_id']]['error'], 'HOTEL_TENANT_MISMATCH', j)
        s, j = http(self.base, 'POST', '/api/sync/ops', {'batch': [env]}, self.h(code=code_b))
        self.assertEqual(s, 401, "hotel A's key cannot write to hotel B")
        self.assertEqual(self.report('credit-notes')['credit_notes'], [])

    def test_06_out_of_order_stale_conflicting_and_invalid(self):
        self.disp.url = DEAD
        b = self.bill()
        cn = self.save_cn(self.cn_doc(b, [(0, 1)], 'Cash'))
        rows = self.store.sdb.con().execute('SELECT payload FROM sync_outbox WHERE sent_at IS NULL ORDER BY seq').fetchall()
        cn_env = json.loads(rows[-1][0])
        s, j = http(self.base, 'POST', '/api/sync/ops', {'batch': [cn_env]}, self.h())             # credit note before its bill
        self.assertEqual(j['results'][cn_env['op_id']]['status'], 'committed', j)
        self.assertEqual(self.report('credit-notes')['summary']['original_bill_not_in_cloud'], 1, 'flagged for review, not lost')
        self.disp.url = self.base
        self.drain()
        self.assertEqual(self.report('credit-notes')['summary']['original_bill_not_in_cloud'], 0, 'linked once the bill arrived')
        self.queue_raw(f'chg-{self.tag}', [dict(cn, total=50.0, taxable=47.62, tax=2.38)])          # changed after posting
        self.queue_raw(f'old-{self.tag}', [cn], version=cn_env['doc_version'] - 1)                     # older version
        self.queue_raw(f'nobill-{self.tag}', [dict(self.cn_doc(b, [(0, 1)]), billId='')])           # no original bill
        self.queue_raw(f'badno-{self.tag}', [dict(self.cn_doc(b, [(0, 1)]), billNo=999999)])        # wrong bill number
        self.queue_raw(f'mode-{self.tag}', [dict(self.cn_doc(b, [(0, 1)]), refund='Voucher')])      # unknown refund type
        self.bill()
        self.drain()
        self.assertEqual(self.pending(), 0, 'every rejected op held; the later bill went through')
        self.assertEqual(self.held(), {f'chg-{self.tag}': 'CREDIT_NOTE_IMMUTABLE', f'old-{self.tag}': 'CONFLICT_STALE_RECORD',
                                       f'nobill-{self.tag}': 'INVALID_CREDIT_NOTE', f'badno-{self.tag}': 'INVALID_CREDIT_NOTE',
                                       f'mode-{self.tag}': 'INVALID_CREDIT_NOTE'})
        # A further op on the same credit note waits for the review of the open conflict (SYNC-001); other ops still flow
        self.queue_raw(f'again-{self.tag}', [cn])
        self.bill()
        self.drain()
        self.assertEqual([r[0] for r in self.store.sdb.con().execute('SELECT ref FROM sync_outbox WHERE sent_at IS NULL')], [f'again-{self.tag}'])
        self.assertEqual(self.disp.dispatch_once()['status'], 'blocked_on_dependency')
        other = json.loads(self.store.sdb.con().execute("SELECT other FROM sync_conflicts WHERE rid = ?", (f'chg-{self.tag}',)).fetchone()[0])
        self.assertEqual(other['payload']['records']['cnotes']['ups'][0]['total'], 50, 'rejected payload kept for review')
        reg = self.report('credit-notes')
        self.assertEqual([(c['id'], c['total_p']) for c in reg['credit_notes']], [(cn['id'], 10500)], 'posted credit note unchanged')
        self.assert_parity()

    def test_07_legacy_counter_held_op_with_credit_note_is_recovered(self):
        # A counter before Phase 3.5d sent one op per save with every key; a credit-note save also wrote 'staff'.
        b = self.bill()
        self.drain()
        cn = self.cn_doc(b, [(0, 2)], 'none')
        env = S.make_sync_envelope(f'legacy-{self.tag}', self.code, 'counter', self.store.version + 10, 1, writes_rec={'cnotes': ('spec', [cn], [])})
        env['payload']['values']['staff'] = [{'id': 's1', 'name': 'Ravi'}]
        canon = json.dumps(env['payload'], sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        env['integrity']['checksum'] = 'sha256:' + hashlib.sha256(canon.encode()).hexdigest()
        with self.store.sdb.tx() as c:
            S.SqliteDoc.append_outbox(c, 'ops', env['op_id'], env['doc_version'], env)
            c.execute("INSERT INTO credit_notes (id, ord, no, \"billId\", date, total, extra) VALUES (?, 999, ?, ?, ?, ?, ?)",
                      (cn['id'], cn['no'], b['id'], cn['date'], cn['total'], json.dumps({k: v for k, v in cn.items() if k not in ('id', 'no', 'billId', 'date', 'total')})))
        self.drain()
        self.assertEqual(self.held(), {env['op_id']: 'UNSUPPORTED_BUSINESS_MODULE'})
        plan = S.plan_held_op_replay(self.store.sdb)
        self.assertEqual([sorted(i['envelope']['payload']['records']) for i in plan['replay']], [['cnotes']], 'credit note is now cloud data')
        S.apply_held_op_replay(self.store.sdb, plan)
        self.drain()
        self.assertEqual([c['id'] for c in self.report('credit-notes')['credit_notes']], [cn['id']])
        self.assert_parity()


if __name__ == '__main__':
    unittest.main(verbosity=2)
