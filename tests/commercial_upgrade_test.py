"""Commercial release: an existing customer's data folder opens on the new build with nothing lost or changed.

Synthetic copy of a typical counter folder (legacy JSON storage, the v1.0 default): bills, payments, menu, stock, staff
access, printer settings, hotel ID, licence / subscription, SaaS config, credit notes, daily backup. Checks:
  * the legacy JSON store opens it and every business key is unchanged (credentials only move into hashes);
  * a restart changes nothing;
  * no SQLite file or storage flag is created (no silent engine change);
  * the verified opt-in SQLite migration keeps the same business data.

    python tests/commercial_upgrade_test.py
"""
import copy
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['SETU_BACKUP'] = 'off'
os.environ.setdefault('SETU_CLOUD_URL', 'http://127.0.0.1:9')
os.environ.pop('SETU_STORAGE', None)
import app_main as A                      # noqa: E402
import setu_sqlite as S                   # noqa: E402
import setu_migrate as M                  # noqa: E402
import setu_security as SEC               # noqa: E402
from sqlite_phase2_test import sample_doc  # noqa: E402

BUSINESS = ('bills', 'txns', 'menu', 'stock', 'moves', 'kots', 'cnotes', 'kaccha', 'custList', 'att', 'cash', 'salarySheets',
            'subscription', 'saas', 'seq', 'orders', 'waMessages')


def customer_doc():
    d = sample_doc(40)
    d['settings'].update(hotelId='CUST01', name='Old Customer Restaurant', billPrinter='EPSON TM-T82', kotPrinter='KITCHEN-58',
                         printMode='graphic', printAuto=True, paper='58', gstin='09AAACH7409R1ZZ', adminPin='6409', cashierPin='5181')
    d['auth'].update(hotelId='CUST01', ownerName='Asha', password='Owner#2026')
    d['staff'] = [{'id': 's1', 'name': 'Ravi', 'access': 'cashier', 'pin': '3711'}, {'id': 's2', 'name': 'Meena', 'access': 'captain', 'pin': '9024'}]
    d['subscription'] = {'status': 'active', 'planName': 'Premium', 'validUntil': '2027-03-31T00:00:00.000Z', 'usedKeys': ['AD-XXXX'], 'isLifetime': False}
    d['saas'] = {'features': {'gst': True, 'qr': True}, 'webMax': 5}
    d['cnotes'] = [{'id': 'cn1', 'no': 1, 'date': '2026-01-05', 'billId': 'b1', 'billNo': 2, 'taxable': 100, 'tax': 5, 'total': 105, 'refund': 'Cash'}]
    return d


def folder_with(doc):
    folder = tempfile.mkdtemp(prefix='horeca-upgrade-')
    with open(os.path.join(folder, 'setu-db.json'), 'w', encoding='utf-8') as f:
        json.dump({'version': 812, 'savedAt': 1762000000000, 'data': doc}, f, ensure_ascii=False)
    os.makedirs(os.path.join(folder, 'Backups'))
    with open(os.path.join(folder, 'Backups', 'setu-2026-11-01.json'), 'w', encoding='utf-8') as f:
        json.dump({'version': 800, 'savedAt': 1, 'data': doc}, f)
    return folder


class ExistingCustomerUpgrade(unittest.TestCase):
    def setUp(self):
        self.orig = customer_doc()
        self.folder = folder_with(copy.deepcopy(self.orig))

    def check_business(self, data):
        for k in BUSINESS:
            if k in self.orig:
                self.assertEqual(data.get(k), self.orig[k], f'{k} changed')
        st = data['settings']
        for k in ('hotelId', 'name', 'billPrinter', 'kotPrinter', 'printMode', 'printAuto', 'paper', 'gstin'):
            self.assertEqual(st.get(k), self.orig['settings'][k], f'settings.{k} changed')
        self.assertEqual([(s['id'], s['access']) for s in data['staff']], [('s1', 'cashier'), ('s2', 'captain')], 'staff access kept')

    def test_legacy_json_opens_unchanged_and_stays_json(self):
        store = A.open_store(self.folder)
        self.assertIs(type(store), A.SetuStore, 'v1.0 default storage stays the legacy JSON file')
        self.check_business(store.data())
        d = store.data()
        # Credentials moved into salted hashes, still valid
        self.assertTrue(store.check_pin('3711'))
        self.assertTrue(SEC.check_master(d, 'Owner#2026'))
        self.assertGreaterEqual(store.version, 812)
        v = store.version
        again = A.open_store(self.folder)                                       # restart
        self.assertEqual(again.version, v, 'a restart writes nothing')
        self.check_business(again.data())
        self.assertFalse(os.path.exists(os.path.join(self.folder, S.DB_FILE)), 'no SQLite file created on a customer PC')
        self.assertEqual(S.read_flag(self.folder).get('engine'), None, 'no storage flag written')
        self.assertTrue(os.path.exists(os.path.join(self.folder, 'Backups', 'setu-2026-11-01.json')), 'old backups kept')

    def test_opt_in_sqlite_migration_keeps_business_data(self):
        A.open_store(self.folder)                                                # first start on JSON, like the counter
        rep = M.migrate(self.folder, cutover=True)
        self.assertEqual(rep['status'], 'MIGRATED', rep)
        store = A.open_store(self.folder)
        self.assertIs(type(store), A.SqliteSetuStore)
        try:
            data = store.data()
            data['bills'] = list(store.sdb.get_records(store.sdb.con(), 'bills', [b['id'] for b in self.orig['bills']]).values())
            data['bills'].sort(key=lambda b: [x['id'] for x in self.orig['bills']].index(b['id']))
            self.check_business(data)
            self.assertTrue(store.check_pin('9024'))
        finally:
            store.sdb.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
