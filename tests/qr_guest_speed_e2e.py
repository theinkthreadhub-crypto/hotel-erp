"""Table QR on a hotel whose cloud copy holds many bills (BUG-0036): the guest pages (menu, status, call waiter) must not
read the whole hotel copy on every tap; a menu change on the counter must still reach the guest at once; a second
"Call waiter" answers with the open call.

Local Worker (Miniflare), synthetic hotel, test-only ADMIN_KEY. Never production.

    python tests/qr_guest_speed_e2e.py     # needs cloud/node_modules (npm ci in cloud/)
"""
import json
import os
import statistics
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phase35d_local_e2e import WRANGLER, LoopbackBase, http  # noqa: E402


@unittest.skipUnless(os.path.exists(WRANGLER), 'cloud/node_modules missing: run npm ci in cloud/ (SKIPPED, not passed)')
class GuestQrSpeed(LoopbackBase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_guest_pages_fast_and_fresh(self):
        code, key = self.new_hotel('Q')
        H = {'X-Setu-Hotel': code, 'X-Setu-Sync': key, 'X-Setu-Caps': 'secure1'}
        doc = {'settings': {'name': 'Busy Dhaba', 'gst': 5}, 'menu': [{'id': f'm{i}', 'name': f'Dish {i}', 'price': 100 + i, 'cat': 'Main'} for i in range(80)],
               'bills': [{'id': f'b{i}', 'idemKey': f'idem_b{i}', 'no': i + 1, 'date': '2026-11-01', 'time': '12:00', 'mode': 'Cash', 'total': 210, 'sub': 200,
                          'tax': 10, 'items': [{'mid': 'm1', 'name': 'Dish 1', 'price': 200, 'qty': 1}], 'used': [], 'cust': 'Guest', 'phone': '9876500000'}
                         for i in range(80000)]}
        s, j = http(self.base, 'POST', '/api/db', {'baseVersion': 0, 'data': doc}, H, timeout=300)
        self.assertEqual(s, 200, j)
        s, j = http(self.base, 'POST', '/api/qr/table', {'table': 'T-1', 'action': 'new'}, H)
        tok = j['tables']['T-1']['token']
        G = {'X-Setu-Hotel': code}

        def timed(method, path, body=None):
            t = time.time()
            s2, r = http(self.base, method, path, body, G, timeout=120)
            self.assertEqual(s2, 200, r)
            return (time.time() - t) * 1000, r

        first, menu = timed('GET', f'/api/guest/menu?t={tok}')
        self.assertEqual(len(menu['items']), 80)
        later = [timed('GET', f'/api/guest/menu?t={tok}')[0] for _ in range(4)] + [timed('GET', f'/api/guest/status?t={tok}')[0] for _ in range(4)]
        med = statistics.median(later)
        self.assertLess(med, first / 4, f'guest pages read the whole hotel copy on every tap (first {first:.0f} ms, then median {med:.0f} ms)')
        # Call waiter twice: one call, both answered
        _, c1 = timed('POST', '/api/guest/call', {'t': tok, 'kind': 'waiter'})
        _, c2 = timed('POST', '/api/guest/call', {'t': tok, 'kind': 'waiter'})
        self.assertEqual((c2.get('again'), c2['id']), (True, c1['id']))
        # A menu change on the counter reaches the guest at once (no stale copy)
        s, cur = http(self.base, 'GET', '/api/db', None, H, timeout=120)
        data = cur['data']
        data['menu'][0]['price'] = 999
        data['menu'].append({'id': 'mnew', 'name': 'Masala Chai', 'price': 30, 'cat': 'Drinks'})
        s, j = http(self.base, 'POST', '/api/db', {'baseVersion': cur['version'], 'data': data}, H, timeout=300)
        self.assertEqual(s, 200, j)
        _, menu2 = timed('GET', f'/api/guest/menu?t={tok}')
        prices = {m['id']: m['price'] for m in menu2['items']}
        self.assertEqual((prices.get('m0'), prices.get('mnew')), (999, 30), 'the guest sees the new menu')


if __name__ == '__main__':
    unittest.main(verbosity=2)
