"""HoReCa One v1.0 QA — database safety across both storage engines (synthetic customer data only).

One fingerprint of the business data (bill count, totals per payment mode in paise, tax, credit dues per customer,
menu + prices, stock, staff access, hotel ID, licence) must be identical at every step:
  legacy JSON open -> verified SQLite migration -> SQLite backup (SHA-256) -> restore to an isolated folder
  -> rollback export to legacy JSON -> JSON open again. A restore for the wrong hotel is refused.

    python tests/qa_db_safety_test.py
"""
import copy
import gzip
import hashlib
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
from commercial_upgrade_test import customer_doc  # noqa: E402

P = lambda v: int(round(float(v or 0) * 100))


def fingerprint(d):
    bills = [b for b in d['bills'] if not b.get('cancelled')]
    by_mode = {}
    for b in bills:
        for p in (b.get('pays') or [{'mode': b.get('mode'), 'amt': b.get('total')}]):
            by_mode[p['mode']] = by_mode.get(p['mode'], 0) + P(p['amt'])
    dues = {}
    for b in bills:
        if b.get('mode') == 'Credit':
            dues[b.get('phone')] = dues.get(b.get('phone'), 0) + P(b.get('total'))
    return {
        'bills': len(d['bills']), 'cancelled': sum(1 for b in d['bills'] if b.get('cancelled')),
        'by_mode_p': by_mode, 'tax_p': sum(P(b.get('tax')) for b in bills), 'total_p': sum(P(b.get('total')) for b in bills),
        'credit_dues_p': dues, 'menu': sorted((m['id'], P(m.get('price'))) for m in d['menu']),
        'stock': sorted((s['id'], round(float(s.get('qty') or 0), 3)) for s in d['stock']),
        'staff': sorted((s['id'], s.get('access') or s.get('role')) for s in d['staff']),
        'hotel': (d['settings'].get('hotelId'), d['auth'].get('hotelId')), 'licence': d.get('subscription'),
        'cnotes': [(c['id'], P(c['total'])) for c in d.get('cnotes') or []],
    }


def legacy_folder(doc):
    folder = tempfile.mkdtemp(prefix='horeca-dbsafety-')
    with open(os.path.join(folder, 'setu-db.json'), 'w', encoding='utf-8') as f:
        json.dump({'version': 500, 'savedAt': 1, 'data': doc}, f, ensure_ascii=False)
    return folder


class DatabaseSafety(unittest.TestCase):
    def setUp(self):
        doc = customer_doc()
        for i, b in enumerate(doc['bills']):          # some on account (customer dues)
            if i % 7 == 3:
                b.update(mode='Credit', phone='98765000%02d' % (i % 3))
        self.doc = doc
        self.expected = fingerprint(copy.deepcopy(doc))

    def test_json_sqlite_backup_restore_rollback_keep_every_figure(self):
        folder = legacy_folder(copy.deepcopy(self.doc))
        js = A.open_store(folder)
        self.assertIs(type(js), A.SetuStore)
        self.assertEqual(fingerprint(js.data()), self.expected, 'legacy JSON open')

        rep = M.migrate(folder, cutover=True)
        self.assertEqual(rep['status'], 'MIGRATED', rep)
        sq = A.open_store(folder)
        self.assertIs(type(sq), A.SqliteSetuStore)
        self.assertEqual(fingerprint(sq.sdb.export_document()), self.expected, 'after verified SQLite migration')

        bdir = tempfile.mkdtemp(prefix='horeca-bk-')
        info = sq.sdb.backup_to(os.path.join(bdir, 'setu-backup.sqlite.gz'))
        with gzip.open(info['file'], 'rb') as f:    # the manifest checksum is of the uncompressed snapshot
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), info['sha256'], 'backup checksum matches the snapshot')
        self.assertTrue(info['verified'])
        sq.sdb.close()

        iso = os.path.join(tempfile.mkdtemp(prefix='horeca-restore-'), 'restored')
        os.makedirs(iso)
        with self.assertRaises(Exception):
            S.restore_backup(info['file'], os.path.join(iso, S.DB_FILE), expected_hotel_id='OTHER9')
        S.restore_backup(info['file'], os.path.join(iso, S.DB_FILE), expected_hotel_id='CUST01')
        restored = S.SqliteDoc(os.path.join(iso, S.DB_FILE))
        self.assertEqual(fingerprint(restored.export_document()), self.expected, 'restore to an isolated folder')
        restored.close()

        rb = legacy_folder({})                          # rollback target: a fresh legacy JSON folder
        out = M.export_json(folder, os.path.join(rb, 'setu-db.json'))
        self.assertEqual(out['bills'], self.expected['bills'])
        back = A.open_store(rb)
        self.assertIs(type(back), A.SetuStore)
        self.assertEqual(fingerprint(back.data()), self.expected, 'rollback export opened as legacy JSON')

    def test_json_daily_backup_is_a_full_copy(self):
        folder = legacy_folder(copy.deepcopy(self.doc))
        js = A.open_store(folder)
        cur = js.data()
        cur['seq']['bill'] += 0
        js.write(cur)
        copies = [x for x in os.listdir(os.path.join(folder, 'Backups')) if x.startswith('setu-') and x.endswith('.json')]
        self.assertTrue(copies, 'daily backup copy written')
        with open(os.path.join(folder, 'Backups', copies[-1]), encoding='utf-8') as f:
            self.assertEqual(fingerprint(json.load(f)['data']), self.expected)


if __name__ == '__main__':
    unittest.main(verbosity=2)
