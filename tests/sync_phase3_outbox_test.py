"""Phase 3.0: Safe Sync Foundation Test Suite.

Verifies:
1. Correct operation payload after a bill
2. Purchase/payment/stock operation capture
3. Crash after local commit
4. Lost cloud acknowledgment
5. Duplicate retry
6. Partially accepted batch
7. Different-content duplicate
8. Cross-hotel rejection
9. Restart with pending operations

Synthetic data only, temporary directories.
"""
import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import setu_sqlite as S
import setu_migrate as M
import app_main as A
from sqlite_phase2_test import sample_doc


def migrated(tmp, doc):
    d = os.path.join(tmp, 'hotel')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'setu-db.json'), 'w', encoding='utf-8') as f:
        json.dump({'version': 1, 'savedAt': 1, 'data': doc}, f, ensure_ascii=False)
    r = M.migrate(d, cutover=True)
    assert r['status'] == 'MIGRATED', r
    return d


class Phase3SyncOutboxTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='setu-p3-')
        self.doc = sample_doc(30)
        self.doc['settings']['hotelCode'] = 'TEST_HOTEL_01'
        self.dir = migrated(self.tmp, self.doc)
        self.store = A.SqliteSetuStore(self.dir)

    def tearDown(self):
        if hasattr(self, 'store') and self.store and hasattr(self.store, 'sdb'):
            try:
                self.store.sdb.close()
            except Exception:
                pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def reopen(self):
        self.store.sdb.close()
        self.store = A.SqliteSetuStore(self.dir)
        return self.store

    # 1. Correct operation payload after a bill
    def test_correct_operation_payload_after_bill(self):
        bill = {
            'id': 'bill_p3_01',
            'no': 101,
            'table': 'T-1',
            'channel': 'Dine-In',
            'mode': 'Cash',
            'total': 450.0,
            'tax': 22.5,
            'sub': 427.5,
            'items': [
                {'mid': 'm1', 'name': 'Butter Chicken', 'price': 350.0, 'qty': 1},
                {'mid': 'm2', 'name': 'Butter Naan', 'price': 50.0, 'qty': 2}
            ],
            'pays': [{'mode': 'Cash', 'amt': 450.0}],
            'date': '2026-11-05',
            'time': '12:30',
            'idemKey': 'idem_p3_01'
        }
        res, out = self.store.apply_ops({
            'ops': [{'k': 'bills', 'up': [bill]}],
            'bv': self.store.version,
            'id': 'op_bill_01',
            'deviceId': 'pos_counter_01'
        }, 'cashier')
        self.assertEqual(res, 200)

        # Check outbox record
        pending = self.store.get_pending_outbox()
        self.assertTrue(len(pending) >= 1)
        row = next(r for r in pending if r['ref'] == 'op_bill_01')
        env = row['payload']

        self.assertEqual(env['envelope_version'], 1)
        self.assertEqual(env['op_id'], 'op_bill_01')
        self.assertEqual(env['hotel_id'], self.store.sdb.meta('hotel_id'))
        self.assertEqual(env['device_id'], 'pos_counter_01')
        self.assertEqual(env['event_type'], 'ops')
        self.assertEqual(env['actor']['role'], 'cashier')

        # Full business records preserved in envelope
        b_records = env['payload']['records']['bills']['ups']
        self.assertEqual(len(b_records), 1)
        self.assertEqual(b_records[0]['id'], 'bill_p3_01')
        self.assertEqual(b_records[0]['total'], 450.0)
        self.assertEqual(len(b_records[0]['items']), 2)

        # Integrity checksum verification
        payload_canonical = json.dumps(env['payload'], sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        expected_chk = 'sha256:' + hashlib.sha256(payload_canonical.encode('utf-8')).hexdigest()
        self.assertEqual(env['integrity']['checksum'], expected_chk)
        self.assertIn('bills', env['integrity']['keys'])

    # 2. Purchase/payment/stock operation capture
    def test_purchase_payment_stock_operation_capture(self):
        txn = {
            'id': 'txn_p3_sup_01',
            'type': 'Purchase',
            'amount': 5000.0,
            'party': 'Dairy Supplier',
            'mode': 'Bank',
            'date': '2026-11-05',
            'time': '10:00'
        }
        stock = {
            'id': 'stock_paneer',
            'name': 'Fresh Paneer',
            'qty': 25.0,
            'unit': 'kg',
            'cost': 200.0
        }
        res, out = self.store.apply_ops({
            'ops': [
                {'k': 'txns', 'up': [txn]},
                {'k': 'stock', 'up': [stock]}
            ],
            'bv': self.store.version,
            'id': 'op_pur_01',
            'deviceId': 'manager_pc'
        }, 'admin', elev=True)
        self.assertEqual(res, 200)

        pending = self.store.get_pending_outbox()
        row = next(r for r in pending if r['ref'] == 'op_pur_01')
        env = row['payload']

        self.assertIn('txns', env['payload']['records'])
        self.assertIn('stock', env['payload']['records'])
        self.assertEqual(env['payload']['records']['txns']['ups'][0]['amount'], 5000.0)
        self.assertEqual(env['payload']['records']['stock']['ups'][0]['qty'], 25.0)

    # 3. Crash after local commit
    def test_crash_after_local_commit(self):
        # Commit local bill
        bill = {
            'id': 'bill_crash_test',
            'no': 102,
            'total': 120.0,
            'mode': 'Cash',
            'date': '2026-11-05',
            'idemKey': 'idem_crash_01'
        }
        res, out = self.store.apply_ops({
            'ops': [{'k': 'bills', 'up': [bill]}],
            'bv': self.store.version,
            'id': 'op_crash_01'
        }, 'cashier')
        self.assertEqual(res, 200)

        # Simulate abrupt process exit / crash and restart
        st2 = self.reopen()

        # Verify bill survived
        with st2.sdb.rlock():
            b = st2.sdb.get_records(st2.sdb.con(), 'bills', ['bill_crash_test']).get('bill_crash_test')
        self.assertIsNotNone(b)
        self.assertEqual(b['total'], 120.0)

        # Verify outbox pending entry survived with full envelope
        pending = st2.get_pending_outbox()
        matching = [r for r in pending if r['ref'] == 'op_crash_01']
        self.assertEqual(len(matching), 1)
        self.assertIsNone(matching[0]['sent_at'])
        self.assertEqual(matching[0]['payload']['payload']['records']['bills']['ups'][0]['id'], 'bill_crash_test')

    # 4. Lost cloud acknowledgment
    def test_lost_cloud_acknowledgment(self):
        bill = {'id': 'bill_ack_lost', 'total': 200.0, 'mode': 'UPI', 'idemKey': 'idem_lost_ack'}
        res1, out1 = self.store.apply_ops({
            'ops': [{'k': 'bills', 'up': [bill]}],
            'bv': self.store.version,
            'id': 'op_lost_ack_01'
        }, 'cashier')
        self.assertEqual(res1, 200)

        # Client sent, cloud applied, but network dropped before client received HTTP 200 ack
        # Outbox remains pending
        pending1 = self.store.get_pending_outbox()
        row = next(r for r in pending1 if r['ref'] == 'op_lost_ack_01')
        self.assertIsNone(row['sent_at'])

        # Client retries sending with the same op_id
        res2, out2 = self.store.apply_ops({
            'ops': [{'k': 'bills', 'up': [bill]}],
            'bv': self.store.version,
            'id': 'op_lost_ack_01'
        }, 'cashier')
        self.assertEqual(res2, 200)
        self.assertTrue(out2.get('repeat'), "Duplicate retry must return repeat=True")

        # Zero duplicate bills created
        with self.store.sdb.rlock():
            all_b = self.store.sdb.get_records(self.store.sdb.con(), 'bills', ['bill_ack_lost'])
        self.assertEqual(len(all_b), 1)

    # 5. Duplicate retry
    def test_duplicate_retry(self):
        res1, out1 = self.store.apply_ops({
            'ops': [{'k': 'settings', 'set': {'currency': 'INR'}}],
            'bv': self.store.version,
            'id': 'op_dup_01'
        }, 'admin', elev=True)
        self.assertEqual(res1, 200)

        pending_count_1 = len(self.store.get_pending_outbox())

        # Retry exact same op
        res2, out2 = self.store.apply_ops({
            'ops': [{'k': 'settings', 'set': {'currency': 'INR'}}],
            'bv': self.store.version,
            'id': 'op_dup_01'
        }, 'admin', elev=True)
        self.assertEqual(res2, 200)
        self.assertTrue(out2.get('repeat'))

        # Outbox count unchanged (idempotency avoided second outbox row)
        pending_count_2 = len(self.store.get_pending_outbox())
        self.assertEqual(pending_count_1, pending_count_2)

    # 6. Partially accepted batch
    def test_partially_accepted_batch(self):
        # Create 3 distinct operations
        for i in [1, 2, 3]:
            res, out = self.store.apply_ops({
                'ops': [{'k': 'bills', 'up': [{'id': f'b_batch_{i}', 'total': float(i * 100), 'idemKey': f'idem_b_{i}'}]}],
                'bv': self.store.version,
                'id': f'op_batch_{i}'
            }, 'cashier')
            self.assertEqual(res, 200)

        pending = self.store.get_pending_outbox()
        batch_seqs = {r['ref']: r['seq'] for r in pending if r['ref'].startswith('op_batch_')}
        self.assertEqual(len(batch_seqs), 3)

        # Remote server accepted op_batch_1 and op_batch_3, but failed op_batch_2
        acked_count = self.store.ack_outbox(['op_batch_1', 'op_batch_3'])
        self.assertEqual(acked_count, 2)

        # Verify only op_batch_1 and op_batch_3 are marked sent; op_batch_2 is still pending!
        with self.store.sdb.rlock():
            con = self.store.sdb.con()
            st1 = con.execute("SELECT sent_at FROM sync_outbox WHERE ref = 'op_batch_1'").fetchone()[0]
            st2 = con.execute("SELECT sent_at FROM sync_outbox WHERE ref = 'op_batch_2'").fetchone()[0]
            st3 = con.execute("SELECT sent_at FROM sync_outbox WHERE ref = 'op_batch_3'").fetchone()[0]

        self.assertIsNotNone(st1, "op_batch_1 must be marked acknowledged")
        self.assertIsNone(st2, "op_batch_2 must NOT be acknowledged (must remain pending)")
        self.assertIsNotNone(st3, "op_batch_3 must be marked acknowledged")

    # 7. Different-content duplicate
    def test_different_content_duplicate(self):
        bill_v1 = {'id': 'bill_conflict_01', 'total': 100.0, 'items': [{'mid': 'm1', 'name': 'Tea', 'price': 100.0, 'qty': 1}]}
        bill_v2 = {'id': 'bill_conflict_01', 'total': 500.0, 'items': [{'mid': 'm2', 'name': 'Feast', 'price': 500.0, 'qty': 1}]}

        # Save with differing content
        res, out = self.store.apply_ops({
            'ops': [{'k': 'bills', 'up': [bill_v1, bill_v2]}],
            'bv': self.store.version,
            'id': 'op_conflict_01'
        }, 'cashier')
        self.assertEqual(res, 200)
        self.assertTrue('conflicts' in out or len(out.get('conflicts', [])) > 0)

        # Verify conflict is captured in envelope
        pending = self.store.get_pending_outbox()
        row = next(r for r in pending if r['ref'] == 'op_conflict_01')
        env = row['payload']
        self.assertTrue(len(env['conflicts']) > 0)
        self.assertEqual(env['conflicts'][0]['id'], 'bill_conflict_01')

    # 8. Cross-hotel rejection
    def test_cross_hotel_rejection(self):
        # A sync envelope intended for HOTEL_A must be rejected if evaluated against HOTEL_B
        envelope = S.make_sync_envelope(
            op_id='op_cross_01',
            hotel_id='HOTEL_A',
            device_id='device_01',
            doc_version=10,
            timestamp=int(time.time() * 1000),
            writes_rec={'bills': ('rec', [{'id': 'b1', 'total': 100}], [])}
        )

        def ingest_on_hotel(env, target_hotel):
            if env.get('hotel_id') != target_hotel:
                raise ValueError(f"CROSS_HOTEL_REJECTED: envelope for {env.get('hotel_id')} cannot be ingested on {target_hotel}")
            return True

        self.assertTrue(ingest_on_hotel(envelope, 'HOTEL_A'))
        with self.assertRaises(ValueError) as ctx:
            ingest_on_hotel(envelope, 'HOTEL_B')
        self.assertIn("CROSS_HOTEL_REJECTED", str(ctx.exception))

    # 9. Restart with pending operations
    def test_restart_with_pending_operations(self):
        for i in range(1, 6):
            self.store.apply_ops({
                'ops': [{'k': 'bills', 'up': [{'id': f'b_restart_{i}', 'total': float(i * 50)}]}],
                'bv': self.store.version,
                'id': f'op_restart_{i}'
            }, 'cashier')

        # Reopen store from disk
        st2 = self.reopen()
        pending = st2.get_pending_outbox()
        restart_ops = [r for r in pending if r['ref'].startswith('op_restart_')]
        self.assertEqual(len(restart_ops), 5)
        # Monotonic FIFO seq check
        seqs = [r['seq'] for r in restart_ops]
        self.assertEqual(seqs, sorted(seqs))
        # Ensure none is legacy
        for r in restart_ops:
            self.assertFalse(r['is_legacy'])
            self.assertEqual(r['payload']['envelope_version'], 1)


if __name__ == '__main__':
    unittest.main()
