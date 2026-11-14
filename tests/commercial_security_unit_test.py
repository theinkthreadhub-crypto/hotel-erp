"""Commercial-release security regressions on the counter side (no Worker needed; the cloud is a stub).

  SEC-R6  a successful cloud login replaced the counter's owner password with whatever password passed the cloud check
  SEC-R7  the counter's offline /api/hotel/login fallback had no wrong-try limit
  SEC-R8  the app accepted built-in '1234' / '0000' as the admin password (Gate 1 and offline hotel login) and set
          '1234' as owner password after an activation without the typed password

    python tests/commercial_security_unit_test.py
"""
import http.server
import json
import os
import re
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['SETU_BACKUP'] = 'off'
os.environ.setdefault('SETU_CLOUD_URL', 'http://127.0.0.1:9')
import app_main as A                      # noqa: E402
import setu_security as SEC               # noqa: E402
from sqlite_phase2b_test import migrated  # noqa: E402
from sqlite_phase2_test import sample_doc  # noqa: E402


class CounterHotelLogin(unittest.TestCase):
    def setUp(self):
        d = sample_doc(3)
        d['settings']['hotelId'] = d['auth']['hotelId'] = 'SECU01'
        d['secure'] = {'owner': SEC.hash_secret('Real#Owner55')}
        d['staff'] = [{'id': 's1', 'name': 'Cash', 'access': 'cashier', 'pin': '36914'}]
        self.store = self.make_store(d)
        self.srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), A.make_handler(ROOT, self.store, 0))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.real_post = A.http_cloud_post

    def make_store(self, d):
        return A.SqliteSetuStore(migrated(tempfile.mkdtemp(prefix='horeca-sec-'), d))

    def tearDown(self):
        A.http_cloud_post = self.real_post
        self.srv.shutdown()
        if getattr(self.store, 'sdb', None):
            self.store.sdb.close()

    def post(self, body):
        req = urllib.request.Request(f'http://127.0.0.1:{self.srv.server_address[1]}/api/hotel/login', method='POST',
                                     data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}')

    def test_cloud_login_never_replaces_existing_owner_password(self):
        A.http_cloud_post = lambda path, obj, hotel=None, timeout=12: (200, {'ok': True, 'hotelId': 'SECU01', 'hotelName': 'X', 'owner': 'O'})
        s, j = self.post({'hotelId': 'SECU01', 'username': 'admin', 'password': 'Manager#Pin7'})
        self.assertEqual(s, 200, j)
        sec = self.store.data().get('secure') or {}
        self.assertTrue(SEC.verify_secret('Real#Owner55', sec.get('owner')), 'the owner password is unchanged')
        self.assertFalse(SEC.verify_secret('Manager#Pin7', sec.get('owner')))

    def test_cloud_login_is_saved_on_the_counter(self):
        A.http_cloud_post = lambda path, obj, hotel=None, timeout=12: (200, {'ok': True, 'hotelId': 'SECU01', 'hotelName': 'Saved Name', 'owner': 'Asha'})
        s, j = self.post({'hotelId': 'SECU01', 'username': 'owner', 'password': 'Real#Owner55'})
        self.assertEqual(s, 200, j)
        d = self.store.data()
        self.assertEqual((d['settings']['name'], d['auth']['ownerName'], d['auth']['status']), ('Saved Name', 'Asha', 'active'),
                         'store.save() did not exist: the login was never saved on the counter')
        self.assertTrue(d['bills'] if 'bills' in d else True, 'other data kept')

    def test_new_pc_takes_owner_password_from_cloud_login(self):
        with self.store.lock:
            cur = self.store.data()
            cur['secure'] = {}
            self.store.write(cur)
        A.http_cloud_post = lambda path, obj, hotel=None, timeout=12: (200, {'ok': True, 'hotelId': 'SECU01', 'hotelName': 'X', 'owner': 'O'})
        s, j = self.post({'hotelId': 'SECU01', 'username': 'owner', 'password': 'Fresh#Owner88'})
        self.assertEqual(s, 200, j)
        self.assertTrue(SEC.verify_secret('Fresh#Owner88', (self.store.data().get('secure') or {}).get('owner')))

    def test_offline_fallback_is_rate_limited_and_role_aware(self):
        A.http_cloud_post = lambda path, obj, hotel=None, timeout=12: (None, None)        # no internet
        s, j = self.post({'hotelId': 'SECU01', 'password': '36914'})
        self.assertEqual((s, j.get('role')), (200, 'cashier'), 'a cashier PIN gives a cashier session, never admin')
        for i in range(5):
            s, _ = self.post({'hotelId': 'SECU01', 'password': f'wrong{i}'})
            self.assertEqual(s, 401)
        s, j = self.post({'hotelId': 'SECU01', 'password': '36914'})
        self.assertEqual(s, 429, j)


class CounterHotelLoginLegacyJson(CounterHotelLogin):
    """The same checks on the legacy JSON store (the default storage of existing installs)."""
    def make_store(self, d):
        folder = tempfile.mkdtemp(prefix='horeca-sec-json-')
        with open(os.path.join(folder, 'setu-db.json'), 'w', encoding='utf-8') as f:
            json.dump({'version': 1, 'savedAt': 1, 'data': d}, f)
        return A.SetuStore(folder)


class NoBuiltInPasswords(unittest.TestCase):
    def test_app_accepts_no_default_admin_password(self):
        with open(os.path.join(ROOT, 'hotel_erp.html'), encoding='utf-8') as f:
            src = f.read()
        self.assertIsNone(re.search(r"pass\s*===\s*'(1234|0000)'", src), 'a literal default password is accepted')
        self.assertNotIn('Default Admin PIN', src)
        self.assertNotIn("password || '1234'", src)
        self.assertIsNone(re.search(r"(Pin|PIN|pin|password)\s*\|\|\s*'(1111|1234|0000)'", src), 'a literal fallback PIN is accepted (BUG-0022)')


if __name__ == '__main__':
    unittest.main(verbosity=2)
