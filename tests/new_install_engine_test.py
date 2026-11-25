"""New installs start on SQLite (Phase 3, P3-6); a PC that already has data keeps its storage.
Real counter program (app_main.py --server) with SETU_NEW_ENGINE=sqlite, which is what the Windows EXE uses by default.

    python tests/new_install_engine_test.py
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)
os.environ['SETU_BACKUP'] = 'off'
import app_main as A  # noqa: E402


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def http(base, method, path, body=None, headers=None):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), method=method,
                                 headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')


class NewInstallEngine(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='horeca-newinst-')
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            p.kill()
            p.wait(10)

    def start(self, engine='sqlite'):
        tok = 'ni-' + os.urandom(5).hex()
        with open(os.path.join(self.dir, 'setu-devices.json'), 'w', encoding='utf-8') as f:
            json.dump({tok: 'admin'}, f)
        port = free_port()
        p = subprocess.Popen([sys.executable, 'app_main.py', '--server', '--port', str(port), '--data', self.dir], cwd=ROOT,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             env={**{k: v for k, v in os.environ.items() if k != 'SETU_STORAGE'}, 'SETU_NEW_ENGINE': engine,
                                  'SETU_CLOUD_URL': 'http://127.0.0.1:9'})
        self.procs.append(p)
        base = f'http://127.0.0.1:{port}'
        for _ in range(150):
            try:
                if http(base, 'GET', '/api/ping')[0] == 200:
                    break
            except OSError:
                time.sleep(0.2)
        return base, {'X-Setu-Token': tok}

    def test_01_empty_folder_starts_on_sqlite_and_bills(self):
        base, h = self.start()
        s, st = http(base, 'GET', '/api/q/status', None, h)
        self.assertEqual((s, st.get('engine')), (200, 'sqlite'), st)
        self.assertEqual(A.SQ.read_flag(self.dir).get('note'), 'new install')
        # First start of the screen: the starting data is uploaded once, then bills are settled
        s, cur = http(base, 'GET', '/api/db', None, h)
        self.assertEqual(s, 200, cur)
        first = {'settings': {'name': 'New Dhaba', 'gst': 5}, 'menu': [{'id': 'm1', 'name': 'Thali', 'price': 150}], 'seq': {'bill': 0, 'kot': 0}, 'stock': [], 'bills': []}
        s, r = http(base, 'POST', '/api/db', {'baseVersion': cur['version'], 'data': first}, h)
        self.assertEqual(s, 200, r)
        for i in range(3):
            b = {'id': f'ni-{i}', 'table': '', 'channel': 'Takeaway', 'mode': 'Cash', 'items': [{'mid': 'm1', 'name': 'Thali', 'price': 150, 'qty': 1}],
                 'sub': 150, 'tax': 7.5, 'total': 158, 'used': []}
            s, r = http(base, 'POST', '/api/bill/settle', {'idemKey': f'idem-ni-{i}', 'bill': b}, h)
            self.assertEqual(s, 200, r)
        s, q = http(base, 'GET', '/api/q/bills?from=2000-01-01&to=2100-01-01&limit=10', None, h)
        self.assertEqual(sorted(b['no'] for b in q['rows']), [1, 2, 3])

    def test_02_existing_json_data_keeps_json(self):
        with open(os.path.join(self.dir, 'setu-db.json'), 'w', encoding='utf-8') as f:
            json.dump({'version': 7, 'savedAt': 1, 'data': {'settings': {'name': 'Old Hotel'}, 'bills': [{'id': 'b1', 'no': 1, 'total': 100}]}}, f)
        base, h = self.start()
        s, st = http(base, 'GET', '/api/q/status', None, h)
        self.assertNotEqual(st.get('engine'), 'sqlite', 'a PC with data is never moved by itself')
        self.assertFalse(os.path.exists(os.path.join(self.dir, A.SQ.DB_FILE)))

    def test_03_damaged_folder_with_daily_copies_is_a_recovery_not_a_new_install(self):
        os.makedirs(os.path.join(self.dir, 'Backups'))
        with open(os.path.join(self.dir, 'Backups', 'setu-2026-11-20.json'), 'w', encoding='utf-8') as f:
            json.dump({'version': 9, 'savedAt': 1, 'data': {'settings': {'name': 'Old Hotel'}, 'bills': []}}, f)
        base, h = self.start()
        self.assertFalse(os.path.exists(os.path.join(self.dir, A.SQ.DB_FILE)), 'stays on JSON so the daily copy can be used')

    def test_04_source_run_default_stays_json(self):
        old = os.environ.pop('SETU_NEW_ENGINE', None)
        try:
            self.assertEqual(A.new_install_engine(), 'json', 'running from source (development, tests): JSON unless asked')
        finally:
            if old is not None:
                os.environ['SETU_NEW_ENGINE'] = old
        base, h = self.start('json')
        self.assertFalse(os.path.exists(os.path.join(self.dir, A.SQ.DB_FILE)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
