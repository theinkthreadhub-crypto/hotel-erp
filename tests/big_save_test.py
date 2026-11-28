"""A big hotel on the JSON engine: one whole-data save bigger than 200 MB (about 250,000+ bills) must reach setu-db.json.
Before the fix the counter answered 400 "bad request" and the save never reached the file.

Real counter program (app_main.py --server), synthetic data, temporary folder.

    python tests/big_save_test.py
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
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
PY = sys.executable


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def req(base, method, path, body=None, token=''):
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    r = urllib.request.Request(base + path, data=data, method=method, headers={'Content-Type': 'application/json', 'X-Setu-Token': token})
    try:
        with urllib.request.urlopen(r, timeout=600) as res:
            return res.status, json.loads(res.read() or b'{}')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')


class BigSave(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='horeca-bigsave-')
        self.addCleanup(shutil.rmtree, self.dir, True)
        with open(os.path.join(self.dir, 'setu-db.json'), 'w', encoding='utf-8') as f:
            json.dump({'version': 3, 'savedAt': 1, 'data': {'settings': {'name': 'Big Hotel'}, 'bills': [], 'seq': {'bill': 0}}}, f)
        self.token = 'big-save-test-token-' + os.urandom(6).hex()
        with open(os.path.join(self.dir, 'setu-devices.json'), 'w', encoding='utf-8') as f:
            json.dump({self.token: 'admin'}, f)
        self.port = free_port()
        self.base = f'http://127.0.0.1:{self.port}'
        self.proc = subprocess.Popen([PY, 'app_main.py', '--server', '--port', str(self.port), '--data', self.dir], cwd=ROOT,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     env={**os.environ, 'SETU_BACKUP': 'off', 'SETU_CLOUD_URL': 'http://127.0.0.1:9'})
        self.addCleanup(self.proc.kill)
        for _ in range(150):
            try:
                if req(self.base, 'GET', '/api/ping')[0] == 200:
                    break
            except OSError:
                time.sleep(0.2)

    def test_save_bigger_than_200_mb_reaches_the_file(self):
        s, cur = req(self.base, 'GET', '/api/db', token=self.token)
        self.assertEqual(s, 200, cur)
        pad = 'x' * 800
        bills = [{'id': f'b{i}', 'no': i + 1, 'date': '2026-11-01', 'total': 100 + i % 50, 'items': [{'name': 'Dish', 'price': 100, 'qty': 1}],
                  'note': pad} for i in range(260000)]
        data = {**cur['data'], 'bills': bills, 'seq': {'bill': len(bills)}}
        body = json.dumps({'baseVersion': cur['version'], 'force': False, 'removed': [], 'data': data}).encode()
        self.assertGreater(len(body), 200 * 1024 * 1024, 'the save is bigger than the old 200 MB limit')
        s, r = req(self.base, 'POST', '/api/db', body, token=self.token)
        self.assertEqual(s, 200, r)
        with open(os.path.join(self.dir, 'setu-db.json'), encoding='utf-8') as f:
            saved = json.load(f)
        self.assertEqual(len(saved['data']['bills']), 260000, 'every bill is in the counter file')
        self.assertEqual(saved['version'], r['version'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
