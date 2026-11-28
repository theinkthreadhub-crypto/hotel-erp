"""Commercial-release financial report checks against the real local Worker (Miniflare) — synthetic hotels only.

  TD-0014  cloud GST / sales taxable value summed the bill `sub` (before discount; GST-inclusive for inclusive prices)
  TD-0016  cloud expense categories were empty because the app stores the expense head in `head`

    python tests/commercial_finance_e2e.py        # needs cloud/node_modules (npm ci in cloud/)
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phase35d_local_e2e import A, S, WRANGLER, LoopbackBase, http, migrated, sample_doc  # noqa: E402


@unittest.skipUnless(os.path.exists(WRANGLER), 'cloud/node_modules missing: run npm ci in cloud/ (SKIPPED, not passed)')
class CloudFinanceParity(LoopbackBase):
    def setUp(self):
        self.code, self.key = self.new_hotel('F')
        s, j = http(self.base, 'POST', '/api/login', {'pin': 'Loop@Test2026x'}, {'X-Setu-Hotel': self.code})
        self.assertEqual(s, 200, j)
        self.tok = j['token']
        d = sample_doc(3)
        d['settings']['hotelId'] = d['auth']['hotelId'] = self.code
        self.store = A.SqliteSetuStore(migrated(tempfile.mkdtemp(dir=self.tmp), d))
        self.disp = S.OutboxSyncDispatcher(self.store, url=self.base, hotel=self.code, key=self.key, enabled=True)

    def tearDown(self):
        self.store.sdb.close()

    def report(self, name):
        s, j = http(self.base, 'GET', '/api/reports/' + name, None, {'X-Setu-Hotel': self.code, 'X-Setu-Token': self.tok})
        self.assertEqual(s, 200, j)
        return j

    def settle(self, bid, **b):
        code, r = self.store.settle_bill({'idemKey': 'i-' + bid, 'bill': dict({'id': bid, 'table': '', 'channel': 'Takeaway', 'mode': 'Cash',
                                                                               'items': [{'mid': 'm1', 'name': 'x', 'price': 100, 'qty': 1}],
                                                                               'date': '2026-11-10', 'time': '12:00', 'used': []}, **b)})
        self.assertEqual(code, 200, r)

    def test_gst_taxable_value_after_discount_and_for_inclusive_prices(self):
        # Exclusive GST with a discount: sub 1000, disc 100 -> taxable 900, GST 5% = 45, total 945
        self.settle('f1', sub=1000, disc=100, taxable=900, tax=45, gstRate=5, total=945)
        # Inclusive prices: 1050 including 5% GST -> taxable 1000, GST 50
        self.settle('f2', sub=1050, disc=0, taxable=1000, tax=50, gstRate=5, incl=True, total=1050)
        # No GST
        self.settle('f3', sub=333.33, disc=0, taxable=333.33, tax=0, gstRate=0, total=333.33)
        while self.disp.dispatch_once().get('processed'):
            pass
        gst = self.report('gst')['summary']
        local = sum(int(round(b['taxable'] * 100)) for b in self.store.sdb.get_records(self.store.sdb.con(), 'bills', ['f1', 'f2', 'f3']).values())
        self.assertEqual(gst['total_taxable_p'], 223333)
        self.assertEqual(gst['total_taxable_p'], local, 'cloud GST taxable value equals the counter, in paise')
        self.assertEqual(gst['total_gst_p'], 9500)
        self.assertEqual(self.report('sales')['summary']['net_taxable_p'], 223333)

    def test_expense_head_is_the_category(self):
        with self.store.lock:
            code, r = self.store.apply_ops({'bv': self.store.version, 'ops': [{'k': 'txns', 'up': [
                {'id': 'e1', 'type': 'Expense', 'head': 'Gas', 'amount': 800.5, 'mode': 'Cash', 'date': '2026-11-10'},
                {'id': 'e2', 'type': 'Expense', 'head': 'Gas', 'amount': 199.5, 'mode': 'UPI', 'date': '2026-11-10'},
                {'id': 'e3', 'type': 'Expense', 'head': 'Electricity', 'amount': 1500, 'mode': 'Bank', 'date': '2026-11-10'}]}]}, 'local', True)
        self.assertEqual(code, 200, r)
        while self.disp.dispatch_once().get('processed'):
            pass
        cats = {c['category']: c['total_p'] for c in self.report('expenses')['by_category']}
        self.assertEqual(cats, {'Electricity': 150000, 'Gas': 100000})


if __name__ == '__main__':
    unittest.main(verbosity=2)
