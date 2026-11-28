"""Vendor-issued login (CHG-0035): Super Admin creates the hotel with a Hotel ID and a temporary password, the owner signs in
with them and must choose their own password; self-registration is closed unless the deployment opens it.

Runs against a local Worker (Miniflare, synthetic hotels, test-only ADMIN_KEY), never production.

    python tests/vendor_login_e2e.py        # needs cloud/node_modules (npm ci in cloud/)
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phase35d_local_e2e import ADMIN_KEY, WRANGLER, LoopbackBase, http  # noqa: E402

ADMIN = {'X-Setu-Admin': ADMIN_KEY}
TEMP_RE = re.compile(r'^[A-HJ-NP-Za-km-z2-9]{4}-[A-HJ-NP-Za-km-z2-9]{4}-[A-HJ-NP-Za-km-z2-9]{4}$')


@unittest.skipUnless(os.path.exists(WRANGLER), 'cloud/node_modules missing: run npm ci in cloud/ (SKIPPED, not passed)')
class VendorIssuedLogin(LoopbackBase):
    def setUp(self):
        pass   # cloud-only tests: no counter store

    def tearDown(self):
        pass

    def create(self, **extra):
        body = {'name': 'Sharma Hotel', 'owner': 'R Sharma', 'phone': '9876501234', 'businessType': 'hotel', 'days': 365, 'paid': True}
        body.update(extra)
        s, j = http(self.base, 'POST', '/api/admin/create', body, ADMIN)
        self.assertEqual(s, 200, j)
        return j

    def login(self, code, password, new=None, username='owner'):
        body = {'hotelId': code, 'username': username, 'password': password}
        if new is not None:
            body['newPassword'] = new
        return http(self.base, 'POST', '/api/hotel/password' if new is not None else '/api/hotel/login', body, {'X-Setu-Hotel': code})

    def admin_view(self, code, update=None):
        s, j = http(self.base, 'POST', '/api/admin/hotel', {'code': code, 'update': update or {}}, ADMIN)
        self.assertEqual(s, 200, j)
        return j

    def test_01_self_registration_is_closed_by_default(self):
        s, j = http(self.base, 'POST', '/api/hotel/register', {'hotelName': 'Walk In', 'ownerName': 'Some One', 'phone': '9876500009',
                                                              'password': 'Good#Pass42'}, {})
        self.assertEqual(s, 403, j)
        self.assertEqual(j.get('code'), 'REGISTRATION_CLOSED')

    def test_02_generated_temporary_password_and_unique_ids(self):
        a, b = self.create(), self.create()
        self.assertNotEqual(a['code'], b['code'], 'every hotel has its own Hotel ID')
        for j in (a, b):
            self.assertRegex(j['ownerPassword'], TEMP_RE)
            self.assertTrue(j['mustChange'])
            self.assertEqual(j['username'], 'owner')
        self.assertNotEqual(a['ownerPassword'], b['ownerPassword'])
        self.assertEqual(self.admin_view(a['code'])['config']['businessType'], 'hotel')
        self.assertNotIn('ownerPassword', self.admin_view(a['code']), 'the password is shown once only')

    def test_03_first_sign_in_must_choose_own_password(self):
        j = self.create()
        code, temp = j['code'], j['ownerPassword']
        s, r = self.login(code, temp)
        self.assertEqual(s, 403, r)
        self.assertEqual(r['code'], 'MUST_CHANGE_PASSWORD')
        self.assertNotIn('token', r)
        self.assertNotIn('syncKey', r, 'no key before the owner has chosen a password')
        self.assertEqual(self.login(code, 'Wrong#Pass99', 'Mine#Pass2026')[0], 401, 'wrong current password')
        s, r = self.login(code, temp, 'abc12')
        self.assertEqual((s, r.get('code')), (400, 'WEAK_NEW_PASSWORD'), r)
        s, r = self.login(code, temp, '999999')
        self.assertEqual((s, r.get('code')), (400, 'WEAK_NEW_PASSWORD'), r)
        s, r = self.login(code, temp, temp)
        self.assertEqual((s, r.get('code')), (400, 'SAME_PASSWORD'), r)
        s, r = self.login(code, temp, 'Mine#Pass2026')
        self.assertEqual(s, 200, r)
        self.assertTrue(r.get('ok') and r.get('token') and r.get('syncKey'))
        self.assertEqual(self.login(code, temp)[0], 401, 'the temporary password stops working')
        s, r = self.login(code, 'Mine#Pass2026')
        self.assertEqual(s, 200, r)
        self.assertFalse(self.admin_view(code)['mustChange'])

    def test_04_typed_password_is_also_temporary(self):
        j = self.create(password='Vendor#Typed42')
        self.assertNotIn('ownerPassword', j, 'a typed password is not echoed back')
        self.assertEqual(self.login(j['code'], 'Vendor#Typed42')[1].get('code'), 'MUST_CHANGE_PASSWORD')

    def test_05_vendor_reset_gives_a_new_temporary_password(self):
        j = self.create()
        code = j['code']
        self.assertEqual(self.login(code, j['ownerPassword'], 'First#Own2026')[0], 200)
        v = self.admin_view(code, {'resetOwnerPassword': True})
        temp = v['ownerPassword']
        self.assertRegex(temp, TEMP_RE)
        self.assertTrue(v['mustChange'])
        self.assertEqual(self.login(code, 'First#Own2026')[0], 401, 'the forgotten password stops working')
        self.assertEqual(self.login(code, temp)[1].get('code'), 'MUST_CHANGE_PASSWORD')
        self.assertEqual(self.login(code, temp, 'Second#Own2026')[0], 200)
        self.assertEqual(self.login(code, 'Second#Own2026')[0], 200)

    def test_06_manager_pin_cannot_change_the_owner_password(self):
        j = self.create()
        code, key = j['code'], j['syncKey']
        self.assertEqual(self.login(code, j['ownerPassword'], 'Owner#Own2026')[0], 200)
        h = {'X-Setu-Hotel': code, 'X-Setu-Sync': key, 'X-Setu-Caps': 'secure1'}
        s, cur = http(self.base, 'GET', '/api/db', None, h)
        self.assertEqual(s, 200, cur)
        data = cur.get('data') or {}
        data.setdefault('settings', {})['adminPin'] = '74102'
        s, r = http(self.base, 'POST', '/api/db', {'baseVersion': cur.get('version', 0), 'data': data}, h)
        self.assertEqual(s, 200, r)
        self.login(code, '74102', 'Taken#Over2026')                 # manager PIN slot: never changes the owner password
        self.assertEqual(self.login(code, 'Taken#Over2026')[0], 401)
        self.assertEqual(self.login(code, 'Owner#Own2026')[0], 200)

    def test_08_same_create_request_many_times_makes_one_hotel(self):
        import concurrent.futures as cf
        s, before = http(self.base, 'POST', '/api/admin/hotels', {}, ADMIN)
        body = {'name': 'Retry Hotel', 'owner': 'Retry Owner', 'phone': '9876509999', 'businessType': 'cafe', 'days': 30, 'paid': True,
                'idemKey': 'k' + os.urandom(6).hex()}
        with cf.ThreadPoolExecutor(6) as ex:                      # six identical requests at the same moment
            res = list(ex.map(lambda _: http(self.base, 'POST', '/api/admin/create', body, ADMIN), range(6)))
        ok = [j for s_, j in res if s_ == 200]
        self.assertTrue(all(s_ in (200, 409) for s_, _ in res), res)
        self.assertEqual(len({j['code'] for j in ok}), 1, 'every answer names the same hotel')
        self.assertEqual(sum(1 for j in ok if j.get('ownerPassword')), 1, 'the temporary password is given once')
        s, again = http(self.base, 'POST', '/api/admin/create', body, ADMIN)  # a retry later
        self.assertEqual((s, again.get('duplicate'), again.get('code')), (200, True, ok[0]['code']))
        self.assertNotIn('ownerPassword', again)
        self.assertNotIn('syncKey', again)
        s, after = http(self.base, 'POST', '/api/admin/hotels', {}, ADMIN)
        self.assertEqual(len(after['hotels']) - len(before['hotels']), 1, 'one hotel in the registry')

    def test_09_same_add_days_operation_applies_once(self):
        import concurrent.futures as cf
        j = self.create()
        code = j['code']
        p0 = self.admin_view(code)['paidUntil']
        body = {'code': code, 'update': {'days': 30, 'amount': 999}, 'opId': 'o' + os.urandom(6).hex()}
        with cf.ThreadPoolExecutor(5) as ex:
            res = list(ex.map(lambda _: http(self.base, 'POST', '/api/admin/hotel', body, ADMIN), range(5)))
        self.assertTrue(all(s_ in (200, 409) for s_, _ in res), res)
        s, _ = http(self.base, 'POST', '/api/admin/hotel', body, ADMIN)            # retried later
        self.assertEqual(s, 200)
        added = round((self.admin_view(code)['paidUntil'] - p0) / 86400000)
        self.assertEqual(added, 30, 'the same Apply adds 30 days once')
        other = dict(body, opId='o' + os.urandom(6).hex())                       # a NEW Apply adds again
        self.assertEqual(http(self.base, 'POST', '/api/admin/hotel', other, ADMIN)[0], 200)
        self.assertEqual(round((self.admin_view(code)['paidUntil'] - p0) / 86400000), 60)

    def test_10_table_qr_codes_use_the_public_address(self):
        j = self.create(password='Qr#Public2026', mustChange=False)
        h = {'X-Setu-Hotel': j['code'], 'X-Setu-Sync': j['syncKey'], 'X-Setu-Caps': 'secure1'}
        s, st = http(self.base, 'GET', '/api/qr/state', None, h)
        self.assertEqual(s, 200, st)
        self.assertEqual(st['base'], 'https://hotel.setupro.in/q/' + j['code'] + '/', 'printed table QR codes point at hotel.setupro.in')

    def test_07_existing_hotels_are_not_forced_to_change(self):
        j = self.create(password='Moved#Customer42', mustChange=False)
        s, r = self.login(j['code'], 'Moved#Customer42')
        self.assertEqual(s, 200, r)


if __name__ == '__main__':
    unittest.main(verbosity=2)
