"""Phase 3.5e unit checks that run without the Worker (the real-Worker flows are in tests/phase35e_credit_note_e2e.py).

    python tests/phase35e_credit_note_unit_test.py
"""
import json
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['SETU_BACKUP'] = 'off'
os.environ.setdefault('SETU_CLOUD_URL', 'http://127.0.0.1:9')
import app_main as A                      # noqa: E402
import setu_sqlite as S                   # noqa: E402
from sqlite_phase2b_test import migrated  # noqa: E402
from sqlite_phase2_test import sample_doc  # noqa: E402


def worker_src():
    with open(os.path.join(ROOT, 'cloud', 'src', 'worker.js'), encoding='utf-8') as f:
        return f.read()


class CreditNotePolicy(unittest.TestCase):
    def test_cnotes_are_cloud_data_in_policy_v2(self):
        self.assertGreaterEqual(S.SYNC_MODULE_POLICY_VERSION, 2)
        self.assertEqual(S.classify_sync_key('records', 'cnotes'), 'cloud')
        self.assertNotIn('cnotes', S.LOCAL_ONLY_MODULES)
        self.assertEqual(S.classify_sync_key('records', 'menu'), 'local', 'menu stays local until its own phase')

    def test_every_permanent_worker_rejection_is_held_not_retried(self):
        """SYNC-004: a rejection code the Worker can return for a record conflict / invalid credit note must be in the
        counter's permanent list, otherwise the op would be resent forever."""
        src = worker_src()
        codes = set(re.findall(r"cnFail\('([A-Z_]+)'", src)) | set(re.findall(r"errType = isSameVer \? '([A-Z_]+)' : '([A-Z_]+)'", src)[0])
        codes |= {'UNSUPPORTED_BUSINESS_MODULE', 'CONFLICT_OP_ID_PAYLOAD_MISMATCH'}
        self.assertTrue({'INVALID_CREDIT_NOTE', 'CREDIT_NOTE_IMMUTABLE', 'CREDIT_NOTE_EXCEEDS_BILL'} <= codes, codes)
        self.assertEqual(codes - S.PERMANENT_SYNC_REJECTIONS, set())

    def test_worker_credit_note_schema_is_additive(self):
        src = worker_src()
        self.assertIn('CREATE TABLE IF NOT EXISTS sync_credit_notes', src)
        self.assertNotRegex(src, r'DROP TABLE[^;]*sync_credit_notes')
        for col in ('taxable_p INTEGER', 'tax_p INTEGER', 'total_p INTEGER'):
            self.assertIn(col, src, 'credit-note money is stored in integer paise')


class CounterCreditNoteRules(unittest.TestCase):
    def setUp(self):
        d = sample_doc(3)
        d['settings']['hotelId'] = d['auth']['hotelId'] = 'CNUNIT'
        self.store = A.SqliteSetuStore(migrated(tempfile.mkdtemp(prefix='horeca-35e-'), d))

    def tearDown(self):
        self.store.sdb.close()

    def save(self, ops):
        with self.store.lock:
            code, r = self.store.apply_ops({'bv': self.store.version, 'ops': ops}, 'local', True)
        self.assertEqual(code, 200, r)

    def cn(self, cid, bill_id, total, refund='Cash'):
        return {'id': cid, 'no': 1, 'date': '2026-11-10', 'billId': bill_id, 'billNo': 1, 'taxable': round(total / 1.05, 2),
                'tax': round(total - round(total / 1.05, 2), 2), 'total': total, 'refund': refund, 'items': []}

    def test_cancel_refused_when_bill_has_credit_note(self):
        self.save([{'k': 'cnotes', 'up': [self.cn('cnA', 'b1', 105.0)]}])
        code, r = self.store.cancel_bill({'billId': 'b1', 'idemKey': 'k1'})
        self.assertEqual(code, 409, r)
        self.assertFalse(self.store.sdb.get_records(self.store.sdb.con(), 'bills', ['b1'])['b1'].get('cancelled'))
        code, r = self.store.cancel_bill({'billId': 'b2', 'idemKey': 'k2'})
        self.assertEqual(code, 200, r)

    def test_credit_note_save_is_one_op_with_its_refund_and_no_secrets(self):
        cn = self.cn('cnB', 'b1', 52.5)
        self.save([{'k': 'cnotes', 'up': [cn]}, {'k': 'txns', 'up': [{'id': 'rfB', 'type': 'Expense', 'head': 'Customer Refund', 'amount': 52.5,
                                                                       'mode': 'Cash', 'date': '2026-11-10', 'cn': 'cnB'}]}])
        env = json.loads(self.store.sdb.con().execute('SELECT payload FROM sync_outbox ORDER BY seq DESC LIMIT 1').fetchone()[0])
        self.assertEqual(sorted(env['payload']['records']), ['cnotes', 'txns'], 'credit note and its refund travel atomically')
        self.assertNotIn('pbkdf2', json.dumps(env))

    def test_local_totals_skip_credit_notes_of_cancelled_bills(self):
        self.save([{'k': 'cnotes', 'up': [self.cn('cnC', 'b1', 105.0), self.cn('cnD', 'b2', 21.0, 'none')]}])
        bills = self.store.sdb.get_records(self.store.sdb.con(), 'bills', ['b2'])
        self.save([{'k': 'bills', 'up': [dict(bills['b2'], cancelled=True)]}])
        t = S.local_synced_credit_note_totals(self.store.sdb)
        self.assertEqual((t['count'], t['total_p'], t['refunded_p']), (1, 10500, 10500))
        self.assertEqual((t['on_cancelled_count'], t['on_cancelled_p']), (1, 2100))


if __name__ == '__main__':
    unittest.main(verbosity=2)
