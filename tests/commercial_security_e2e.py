"""Commercial-release security regressions against the real local Worker (Miniflare) — synthetic hotels only.

Covers the confirmed findings of the release audit:
  SEC-R1  a staff / cashier PIN signed in at /api/hotel/login and received an admin token plus the hotel's Sync Key
  SEC-R2  the supplied username was never checked
  SEC-R3  /api/hotel/login had no wrong-try limit
  SEC-R4  isWeak() held a control character instead of a back-reference: '2222' was not "too simple"
  SEC-R5  /api/hotel/register accepted any 4-character password

    python tests/commercial_security_e2e.py        # needs cloud/node_modules (npm ci in cloud/)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phase35d_local_e2e import ADMIN_KEY, WRANGLER, LoopbackBase, http  # noqa: E402

OWNER_PW = 'Loop@Test2026x'


@unittest.skipUnless(os.path.exists(WRANGLER), 'cloud/node_modules missing: run npm ci in cloud/ (SKIPPED, not passed)')
class CloudAuthSecurity(LoopbackBase):
    def setUp(self):
        self.code, self.key = self.new_hotel('S')
        s, cur = http(self.base, 'GET', '/api/db', None, self.sync_h())
        self.assertEqual(s, 200, cur)
        # Synthetic staff: a cashier and a captain with their own PINs, the shared cashier PIN, a manager admin PIN
        data = {'settings': {'name': 'Security Test', 'hotelId': self.code, 'cashierPin': '58213', 'adminPin': '74102'},
                'staff': [{'id': 's1', 'name': 'Cash One', 'access': 'cashier', 'pin': '36914'},
                          {'id': 's2', 'name': 'Captain', 'access': 'captain', 'pin': '25803'}],
                'bills': []}
        s, j = http(self.base, 'POST', '/api/db', {'baseVersion': cur.get('version', 0), 'data': data}, self.sync_h())
        self.assertEqual(s, 200, j)

    def tearDown(self):
        pass   # no counter store in these cloud-only tests

    def sync_h(self):
        return {'X-Setu-Hotel': self.code, 'X-Setu-Sync': self.key, 'X-Setu-Caps': 'secure1'}

    def hotel_login(self, password, username='owner'):
        return http(self.base, 'POST', '/api/hotel/login', {'hotelId': self.code, 'username': username, 'password': password},
                    {'X-Setu-Hotel': self.code})

    def test_01_owner_password_still_signs_in(self):
        s, j = self.hotel_login(OWNER_PW)
        self.assertEqual(s, 200, j)
        self.assertEqual((j['role'], j['syncKey']), ('admin', self.key))
        s, j = self.hotel_login('74102', username='admin')            # the manager admin PIN (owner-level slot)
        self.assertEqual(s, 200, j)

    def test_02_staff_pins_never_get_admin_or_sync_key(self):
        for pin in ('36914', '25803', '58213'):
            s, j = self.hotel_login(pin)
            self.assertEqual(s, 401, (pin, s, j))
            self.assertNotIn('syncKey', j)
            self.assertNotIn('token', j)
        # Staff still sign in where they belong: the PIN screen, with their own role and no Sync Key
        s, j = http(self.base, 'POST', '/api/login', {'pin': '36914'}, {'X-Setu-Hotel': self.code})
        self.assertEqual((s, j.get('role')), (200, 'cashier'), j)
        self.assertNotIn('syncKey', j)

    def test_03_username_is_checked(self):
        s, j = self.hotel_login(OWNER_PW, username='someone-else')
        self.assertEqual(s, 401, j)
        for u in ('owner', 'Test Owner', '9876543210', ''):
            s, j = self.hotel_login(OWNER_PW, username=u)
            self.assertEqual(s, 200, (u, j))

    def test_04_wrong_tries_are_limited(self):
        for i in range(5):
            s, _ = self.hotel_login(f'wrong-{i}-pass')
            self.assertEqual(s, 401)
        s, j = self.hotel_login(OWNER_PW)
        self.assertEqual(s, 429, 'locked after 5 wrong tries, even with the right password')

    def test_05_repeated_character_pin_is_weak(self):
        s, cur = http(self.base, 'GET', '/api/db', None, self.sync_h())
        data = {'settings': {'name': 'Security Test', 'hotelId': self.code},
                'staff': [{'id': 's3', 'name': 'Weak', 'access': 'cashier', 'pin': '2222'}], 'bills': []}
        s, j = http(self.base, 'POST', '/api/db', {'baseVersion': cur.get('version', 0), 'data': data}, self.sync_h())
        self.assertEqual(s, 200, j)
        s, j = http(self.base, 'POST', '/api/login', {'pin': '2222'}, {'X-Setu-Hotel': self.code})
        self.assertEqual((s, j.get('error')), (403, 'weak pin'), 'one repeated digit is refused over the internet')

    def test_06_register_uses_the_signup_password_policy(self):
        base = {'hotelName': 'Policy Hotel', 'ownerName': 'Policy Owner', 'phone': '9876500000'}
        for weak in ('abcd', '12345', '777777', 'password'):
            s, j = http(self.base, 'POST', '/api/hotel/register', dict(base, password=weak), {})
            self.assertEqual(s, 400, (weak, j))
            self.assertIn('at least 6 characters', j['error'])
        s, j = http(self.base, 'POST', '/api/hotel/register', dict(base, password='Good#Pass42'), {})
        self.assertEqual(s, 200, j)


if __name__ == '__main__':
    unittest.main(verbosity=2)
