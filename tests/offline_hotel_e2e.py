"""Offline hotel (no internet): Super Admin makes the hotel record (Offline) and the licence key for its counter PC in one form,
and later a renewal key. Checks the real key bytes (signature, Install ID, days), the registry list, idempotency and refusals.

Runs against a local Worker (Miniflare) with a test-only signing key pair and synthetic hotels, never production.

    python tests/offline_hotel_e2e.py        # needs cloud/node_modules (npm ci in cloud/)
"""
import base64
import concurrent.futures as cf
import hashlib
import os
import sys
import time
import unittest

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phase35d_local_e2e import ADMIN_KEY, WRANGLER, LoopbackBase, http  # noqa: E402

ADMIN = {'X-Setu-Admin': ADMIN_KEY}
DAY = 86400000
PRIV = ec.generate_private_key(ec.SECP256R1())          # test-only key pair: production keys are never used here
PUB = PRIV.public_key()
PRIV_B64 = base64.b64encode(PRIV.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption())).decode()
PUB_B64 = base64.b64encode(PUB.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)).decode()
B32 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'


def decode_key(key):
    """Same layout as makeLicenseKey()/verifyLicense(): 'SETU' + base32 of 13 payload bytes + 64 signature bytes."""
    text = ''.join(c for c in key.upper() if c in B32)
    assert text.startswith('SETU'), key
    bits = ''.join(format(B32.index(c), '05b') for c in text[4:128])
    raw = bytes(int(bits[i:i + 8], 2) for i in range(0, 77 * 8, 8))
    payload, sig = raw[:13], raw[13:]
    PUB.verify(encode_dss_signature(int.from_bytes(sig[:32], 'big'), int.from_bytes(sig[32:], 'big')), payload, ec.ECDSA(hashes.SHA256()))
    return {'kind': payload[1], 'value': payload[2] << 8 | payload[3], 'ih': payload[4:8]}


def iid_hash(iid):
    return hashlib.sha256(''.join(c for c in iid.upper() if c.isalnum()).encode()).digest()[:4]


def new_iid():
    a = os.urandom(4).hex().upper()
    return f'SETU-{a[:4]}-{a[4:]}'


@unittest.skipUnless(os.path.exists(WRANGLER), 'cloud/node_modules missing: run npm ci in cloud/ (SKIPPED, not passed)')
class OfflineHotel(LoopbackBase):
    EXTRA_VARS = {'LICENSE_PRIVATE_KEY': PRIV_B64, 'LICENSE_PUBKEY': PUB_B64}

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def create(self, iid, plan='1y', **extra):
        body = {'offline': True, 'installId': iid, 'licPlan': plan, 'name': 'Dhaba Offline', 'owner': 'R Yadav', 'phone': '9876502222',
                'businessType': 'restaurant', 'idemKey': 'k' + os.urandom(6).hex()}
        body.update(extra)
        return http(self.base, 'POST', '/api/admin/create', body, ADMIN)

    def reg(self, code):
        s, j = http(self.base, 'POST', '/api/admin/hotels', {}, ADMIN)
        self.assertEqual(s, 200, j)
        return next(h for h in j['hotels'] if h['code'] == code)

    def renew(self, code, plan='1y', op=None):
        return http(self.base, 'POST', '/api/admin/offline/renew', {'code': code, 'licPlan': plan, 'opId': op or 'o' + os.urandom(6).hex()}, ADMIN)

    def days_left(self, code):
        return round((time.mktime(time.strptime(self.reg(code)['lic'][:19], '%Y-%m-%dT%H:%M:%S')) * 1000 - time.time() * 1000 + time.timezone * 1000) / DAY)

    def test_01_one_form_makes_offline_hotel_and_a_real_key(self):
        iid = new_iid()
        s, j = self.create(iid)
        self.assertEqual(s, 200, j)
        self.assertTrue(j['offline'])
        self.assertEqual((j['installId'], j['label'], j['lifetime']), (iid, '1 Year', False))
        k = decode_key(j['key'])                                       # signature checked with the test public key
        self.assertEqual((k['kind'], k['value'], k['ih']), (1, 365, iid_hash(iid)), 'a 365-day key for this PC only')
        h = self.reg(j['code'])
        self.assertEqual((int(h['offmode']), h['iid'], h['plan'], h['status']), (1, iid, 'offline', 'active'))
        self.assertIn(self.days_left(j['code']), (364, 365, 366))
        self.assertNotIn('ownerPassword', j)
        self.assertNotIn('syncKey', j)

    def test_02_no_cloud_login_for_an_offline_hotel(self):
        s, j = self.create(new_iid())
        self.assertEqual(s, 200, j)
        for pw in ('', 'owner', 'Good#Pass42'):
            s2, r = http(self.base, 'POST', '/api/hotel/login', {'hotelId': j['code'], 'username': 'owner', 'password': pw}, {'X-Setu-Hotel': j['code']})
            self.assertNotEqual(s2, 200, r)
            self.assertNotIn('token', r)

    def test_03_many_taps_one_hotel_one_key(self):
        iid = new_iid()
        body = {'offline': True, 'installId': iid, 'licPlan': '6m', 'name': 'Tap Tap Dhaba', 'owner': 'Owner', 'phone': '9876503333',
                'businessType': 'cafe', 'idemKey': 'k' + os.urandom(6).hex()}
        with cf.ThreadPoolExecutor(5) as ex:
            res = list(ex.map(lambda _: http(self.base, 'POST', '/api/admin/create', body, ADMIN), range(5)))
        self.assertTrue(all(s in (200, 409) for s, _ in res), res)
        ok = [j for s, j in res if s == 200]
        self.assertEqual(len({j['code'] for j in ok}), 1)
        self.assertEqual(len({j['key'] for j in ok}), 1, 'a repeat gets the same key, never a second one')
        s, again = http(self.base, 'POST', '/api/admin/create', body, ADMIN)
        self.assertEqual((s, again.get('duplicate'), again['key']), (200, True, ok[0]['key']))
        s, j = http(self.base, 'POST', '/api/admin/hotels', {}, ADMIN)
        self.assertEqual(sum(1 for h in j['hotels'] if h.get('iid') == iid), 1, 'one hotel in the registry')

    def test_04_refusals(self):
        self.assertEqual(self.create('SETU-12')[0], 400, 'bad Install ID')
        self.assertEqual(self.create(new_iid(), plan='forever')[0], 400, 'unknown plan')
        iid = new_iid()
        s, j = self.create(iid)
        self.assertEqual(s, 200, j)
        s, r = self.create(iid, name='Second Shop')
        self.assertEqual(s, 409, r)
        self.assertIn(j['code'], r['error'], 'names the hotel the PC belongs to')

    def test_05_renewal_adds_days_once_per_apply(self):
        iid = new_iid()
        s, j = self.create(iid, plan='1m')
        self.assertEqual(s, 200, j)
        code, d0 = j['code'], self.days_left(j['code'])
        op = 'o' + os.urandom(6).hex()
        with cf.ThreadPoolExecutor(4) as ex:
            res = list(ex.map(lambda _: self.renew(code, '1y', op), range(4)))
        self.assertTrue(all(s in (200, 409) for s, _ in res), res)
        keys = {r['key'] for s, r in res if s == 200}
        self.assertEqual(len(keys), 1, 'one Apply = one key')
        k = decode_key(keys.pop())
        self.assertEqual((k['kind'], k['value'], k['ih']), (1, 365, iid_hash(iid)))
        self.assertEqual(self.days_left(code) - d0, 365, 'days added to the current licence, once')
        self.assertEqual(self.renew(code, '1y', op)[1]['duplicate'], True)
        self.assertEqual(self.days_left(code) - d0, 365, 'a retry adds nothing')
        self.assertEqual(self.renew(code, '3m')[0], 200)               # a NEW Apply adds again
        self.assertEqual(self.days_left(code) - d0, 455)

    def test_06_lifetime(self):
        s, j = self.create(new_iid(), plan='life')
        self.assertEqual(s, 200, j)
        self.assertTrue(j['lifetime'])
        self.assertEqual(decode_key(j['key'])['kind'], 3)
        self.assertEqual(self.reg(j['code'])['lic'], 'lifetime')
        s, r = self.renew(j['code'], '1y')
        self.assertEqual(s, 200, r)
        self.assertEqual(self.reg(j['code'])['lic'], 'lifetime', 'a lifetime licence stays lifetime')

    def test_07_renewal_is_only_for_offline_hotels(self):
        s, j = http(self.base, 'POST', '/api/admin/create', {'name': 'Online Cafe', 'owner': 'O', 'phone': '9876504444', 'businessType': 'cafe',
                                                             'days': 30, 'paid': True}, ADMIN)
        self.assertEqual(s, 200, j)
        s, r = self.renew(j['code'])
        self.assertEqual(s, 400, r)
        self.assertEqual(self.renew('NOSUCH99')[0], 404)
        self.assertEqual(http(self.base, 'POST', '/api/admin/offline/renew', {'code': j['code'], 'licPlan': '1y'}, ADMIN)[0], 400, 'opId required')

    def test_08_key_signature_is_real(self):
        s, j = self.create(new_iid())
        self.assertEqual(s, 200, j)
        bad = j['key'][:-6] + ('A' if j['key'][-6] != 'A' else 'B') + j['key'][-5:]
        with self.assertRaises((InvalidSignature, AssertionError, ValueError)):
            decode_key(bad)

    def test_09_needs_the_admin_key(self):
        s, _ = http(self.base, 'POST', '/api/admin/create', {'offline': True, 'installId': new_iid(), 'licPlan': '1y', 'name': 'X Y', 'owner': 'Z',
                                                             'phone': '9876505555'}, {'X-Setu-Admin': 'wrong'})
        self.assertEqual(s, 401)


if __name__ == '__main__':
    unittest.main(verbosity=2)
