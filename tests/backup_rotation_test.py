"""Counter (JSON engine) daily backup copies: today's copy is plain, older days are compressed (.json.gz), 14 days plus the
first copy of each of 12 months are kept, and a damaged setu-db.json comes back from a compressed copy.

    python tests/backup_rotation_test.py
"""
import gzip
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
os.environ.setdefault('SETU_BACKUP', 'off')
import app_main as A  # noqa: E402


def doc(v, bills):
    return {'version': v, 'savedAt': v, 'data': {'settings': {'name': 'Rotation Hotel'}, 'bills': [{'id': f'b{i}', 'no': i, 'total': 100 + i} for i in range(bills)]}}


class Rotation(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='horeca-rot-')
        self.bk = os.path.join(self.dir, 'Backups')
        os.makedirs(self.bk)
        self.addCleanup(shutil.rmtree, self.dir, True)

    def put(self, day, v, gz=False):
        p = os.path.join(self.bk, f'setu-{day}.json' + ('.gz' if gz else ''))
        with (gzip.open(p, 'wt', encoding='utf-8') if gz else open(p, 'w', encoding='utf-8')) as f:
            json.dump(doc(v, 50), f)
        return p

    def test_01_old_layout_of_60_plain_copies(self):
        today = date(2026, 11, 25)
        days = [(today - timedelta(days=i)).isoformat() for i in range(60)]
        for i, d in enumerate(days):
            self.put(d, 1000 - i)
        before = {d: json.load(open(os.path.join(self.bk, f'setu-{d}.json')))['data'] for d in days[:14]}
        A.rotate_daily_backups(self.bk, today.isoformat())
        left = sorted(os.listdir(self.bk))
        self.assertIn(f'setu-{days[0]}.json', left, "today's copy stays plain")
        for d in days[8:14]:
            self.assertIn(f'setu-{d}.json', left, 'older plain copies (from before the upgrade) are left as they are')
        for d in days[1:8]:
            self.assertIn(f'setu-{d}.json.gz', left)
            self.assertNotIn(f'setu-{d}.json', left, 'compressed, plain removed')
            with gzip.open(os.path.join(self.bk, f'setu-{d}.json.gz'), 'rt', encoding='utf-8') as f:
                self.assertEqual(json.load(f)['data'], before[d], 'same data after compressing')
        kept_days = {n.split('.')[0][5:] for n in left}
        firsts = {'2026-11-01', '2026-10-01', '2026-09-27'}         # first copy of November, October and September (oldest day)
        self.assertEqual(kept_days, set(days[:14]) | firsts, '14 days + the first copy of each month')
        self.assertIn('setu-2026-10-01.json', left, 'an old plain month copy is kept as it is')

    def test_02_size_for_a_big_hotel(self):
        # Day by day, as the counter runs: each day a plain copy is written with the saves, then the rotation runs
        start, plain = date(2026, 10, 1), 0
        for i in range(56):
            today = (start + timedelta(days=i)).isoformat()
            p = self.put(today, i)
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(doc(i, 20000), f)
            plain = os.path.getsize(p)
            A.rotate_daily_backups(self.bk, today)
        after = sum(os.path.getsize(os.path.join(self.bk, x)) for x in os.listdir(self.bk))
        names = sorted(os.listdir(self.bk))
        self.assertEqual(sum(1 for x in names if x.endswith('.json')), 1, "only today's copy is plain")
        self.assertEqual(len(names), 14 + 2, '14 days + the first copy of October and of November')
        old = plain * 56                                            # before: 56 plain copies (60 kept)
        self.assertLess(after, old / 10, f'less than a tenth of the old layout ({after} bytes vs {old})')

    def test_03_months_kept_for_a_year_only(self):
        today = date(2026, 11, 25)
        for m in range(1, 25):                                       # first day of the last 24 months, compressed
            y, mo = divmod(2026 * 12 + 10 - m, 12)
            self.put(date(y, mo + 1, 1).isoformat(), m, gz=True)
        self.put(today.isoformat(), 0)
        A.rotate_daily_backups(self.bk, today.isoformat())
        kept = {x[5:12] for x in os.listdir(self.bk)}
        self.assertNotIn('2024-11', kept, 'two-year-old copy deleted')
        self.assertIn('2026-10', kept)
        self.assertLessEqual(len(kept - {today.isoformat()[:7]}), 14, 'at most 14 newest days + 12 months')

    def test_04_save_keeps_todays_copy_and_compresses_yesterday(self):
        with open(os.path.join(self.dir, 'setu-db.json'), 'w', encoding='utf-8') as f:
            json.dump(doc(5, 100), f)
        y = time.strftime('%Y-%m-%d', time.localtime(time.time() - 86400))
        self.put(y, 4)
        st = A.SetuStore(self.dir)
        d = st.data()
        d['settings']['x'] = 1
        st.write(d)
        today = time.strftime('%Y-%m-%d')
        self.assertTrue(os.path.exists(os.path.join(self.bk, f'setu-{today}.json')), "today's plain copy written with the save")
        for _ in range(100):
            if os.path.exists(os.path.join(self.bk, f'setu-{y}.json.gz')) and not os.path.exists(os.path.join(self.bk, f'setu-{y}.json')):
                break
            time.sleep(0.05)
        self.assertTrue(os.path.exists(os.path.join(self.bk, f'setu-{y}.json.gz')), "yesterday's copy compressed in the background")
        self.assertFalse(os.path.exists(os.path.join(self.bk, f'setu-{y}.json')))

    def test_05_damaged_file_comes_back_from_a_compressed_copy(self):
        self.put('2026-11-20', 77, gz=True)
        self.put('2026-11-10', 60)
        with open(os.path.join(self.dir, 'setu-db.json'), 'w', encoding='utf-8') as f:
            f.write('{"version": 80, "data": {broken')
        st = A.SetuStore(self.dir)
        self.assertEqual(st.version, 77, 'newest readable copy (compressed) used')
        self.assertEqual(len(st.data()['bills']), 50)
        self.assertTrue(any(x.startswith('setu-db.json.corrupt-') for x in os.listdir(self.dir)), 'damaged file kept aside')


if __name__ == '__main__':
    unittest.main(verbosity=2)
