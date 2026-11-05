"""Phase 3: SQLite counter <-> PostgreSQL cloud, end to end. Synthetic data, temporary folders, a local PostgreSQL
test cluster (never a production database).

    SETU_PG_TEST_DSN=postgresql://setu_admin@127.0.0.1:55432/setu_cloud_t python3 tests/phase3_cloud_test.py

The database must already hold cloud/pg/roles.sql, schema.sql and grants.sql. Every table is emptied first.
"""
import copy
import gzip
import json
import os
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import warnings
warnings.simplefilter('ignore', ResourceWarning)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import psycopg                   # noqa: E402
import setu_sqlite as S          # noqa: E402
import setu_security as SEC      # noqa: E402
import setu_cloud_client as CC   # noqa: E402
import app_main as A             # noqa: E402
from sqlite_phase2_test import sample_doc   # noqa: E402
from sqlite_phase2b_test import migrated    # noqa: E402

DSN = os.environ.get('SETU_PG_TEST_DSN', 'postgresql://setu_admin@127.0.0.1:55432/setu_cloud_t')
ADMIN = 'test-admin-key-' + os.urandom(6).hex()
CPORT, SPORT = 8791, 8661
URL = f'http://127.0.0.1:{CPORT}'
DEAD = 'http://127.0.0.1:9'
OWNER_PW = 'Owner@Pass2026'
RESULTS = {}
TABLES = ['hotels', 'counters', 'bills', 'records', 'owner_creds', 'owner_sessions', 'sync_batches', 'commands', 'conflicts',
          'qr_conf', 'qr_tables', 'guest_orders', 'guest_calls', 'backups', 'login_fails']


def req(method, path, body=None, headers=None, url=URL):
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(url + path, data=data, method=method, headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(r, timeout=120) as x:
            return x.status, json.loads(x.read() or b'{}')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')


def admin(method, path, body=None):
    return req(method, path, body, {'X-Admin-Key': ADMIN})


def hotel_doc(hid, nbills=60):
    d = sample_doc(nbills)
    d['auth']['hotelId'] = d['settings']['hotelId'] = hid
    d['settings']['name'] = f'Synthetic {hid}'
    d['secure'] = {'admin': SEC.hash_secret('739146'), 'owner': SEC.hash_secret(OWNER_PW)}
    for m in d['menu']:
        m['active'] = True
    return d


def cloud_doc(hotel, key):
    s, j = req('GET', '/v1/sync/export', None, {'X-Setu-Hotel': hotel, 'X-Setu-Key': key})
    assert s == 200, j
    return j


def bill(i, total=105):
    return {'id': f'p3-{i}', 'table': '', 'channel': 'Takeaway', 'mode': 'Cash', 'items': [{'mid': 'm1', 'name': 'x', 'price': 100, 'qty': 1}],
            'sub': 100, 'tax': 5, 'total': total, 'date': '2026-01-28', 'time': '13:00', 'used': []}


class Phase3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(DSN, autocommit=True) as c:
            c.execute('TRUNCATE ' + ', '.join(TABLES) + ' CASCADE')
        cls.tmp = tempfile.mkdtemp(prefix='setu-p3-')
        env = dict(os.environ, SETU_PG_DSN=DSN, SETU_CLOUD_ADMIN_KEY=ADMIN, SETU_CLOUD_BACKUPS=os.path.join(cls.tmp, 'cloud-backups'))
        cls.svc = subprocess.Popen([sys.executable, os.path.join(ROOT, 'setu_cloud.py'), '--port', str(CPORT)], env=env)
        cls.addClassCleanup(lambda: (cls.svc.kill(), cls.svc.wait()))
        for _ in range(100):
            try:
                if req('GET', '/v1/ping')[0] == 200:
                    break
            except Exception:
                time.sleep(0.1)
        cls.keys = {}
        for hid in ('SYNTH1', 'SYNTH2'):
            s, j = admin('POST', '/v1/admin/hotels', {'hotel': hid, 'name': f'Synthetic {hid}'})
            assert s == 200, j
            cls.keys[hid] = j['syncKey']
        cls.dirs, cls.stores, cls.agents = {}, {}, {}
        for hid in ('SYNTH1', 'SYNTH2'):
            d = migrated(os.path.join(cls.tmp, hid), hotel_doc(hid))
            cls.dirs[hid] = d
            st = A.SqliteSetuStore(d)
            cls.stores[hid] = st
            cls.agents[hid] = CC.CloudAgent(st, {'url': URL, 'hotel': hid, 'key': cls.keys[hid]}, interval=0.2)

    @classmethod
    def tearDownClass(cls):
        for st in cls.stores.values():
            st.sdb.close()
        cls.svc.kill()
        cls.svc.wait()
        shutil.rmtree(cls.tmp, ignore_errors=True)
        out = os.path.join(ROOT, 'tools', 'db-benchmark', 'results', 'phase3', 'phase3-e2e-results.json')
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'w') as f:
            json.dump(RESULTS, f, indent=1)

    def h(self, hid='SYNTH1'):
        return {'X-Setu-Hotel': hid, 'X-Setu-Key': self.keys[hid]}

    def assertCloudEqualsCounter(self, hid):
        st, ag = self.stores[hid], self.agents[hid]
        ag.sync_once()
        self.assertEqual(ag.cursor(), st.version)
        cd = cloud_doc(hid, self.keys[hid])
        local = st.sdb.export_document()
        diff = sorted(k for k in set(cd['data']) | set(local) if S.canonical_hash({'v': cd['data'].get(k)}) != S.canonical_hash({'v': local.get(k)}))
        if diff:
            k = diff[0]
            print('DIFF', diff, 'cloud:', json.dumps(cd['data'].get(k))[:400], 'counter:', json.dumps(local.get(k))[:400])
        self.assertEqual(diff, [], 'cloud copy differs from the counter')
        self.assertEqual(cd['contentSha256'], S.canonical_hash(local))
        return local

    def settle(self, hid, i, total=105):
        code, r = self.stores[hid].settle_bill({'idemKey': f'idem-{hid}-{i}', 'bill': bill(f'{hid}-{i}', total)})
        self.assertEqual(code, 200, r)
        return r

    # ---------------------------------------------------------------- 1. initial copy
    def test_01_initial_snapshot_equals_counter(self):
        for hid in ('SYNTH1', 'SYNTH2'):
            ag = self.agents[hid]
            t = time.time()
            ag.sync_once()
            RESULTS.setdefault('initialSnapshot', {})[hid] = {'seconds': round(time.time() - t, 3), 'bytesOut': ag.state['bytesOut'], 'batches': ag.state['batches']}
            self.assertEqual(ag.state['snapshots'], 1)
            self.assertCloudEqualsCounter(hid)

    # ---------------------------------------------------------------- 2. offline billing, reconnect
    def test_02_offline_billing_then_reconnect(self):
        ag = self.agents['SYNTH1']
        ag.sync_once()
        ag.conf = dict(ag.conf, url=DEAD)
        for i in range(25):
            self.settle('SYNTH1', f'off{i}')
        with self.assertRaises(Exception):
            ag.sync_once()
        self.assertFalse(ag.state['ok'])
        self.assertGreater(ag.pending(), 0, 'offline work must show as pending')
        before = ag.cursor()
        ag.conf = dict(ag.conf, url=URL)
        snaps = ag.state['snapshots']
        local = self.assertCloudEqualsCounter('SYNTH1')
        self.assertEqual(ag.state['snapshots'], snaps, 'reconnect sends only the changes, not a full copy')
        self.assertGreater(ag.cursor(), before)
        self.assertEqual(ag.pending(), 0)
        self.assertEqual(len([b for b in local['bills'] if str(b.get('idemKey', '')).startswith('idem-SYNTH1-off')]), 25)

    # ---------------------------------------------------------------- 3. duplicate requests, older data
    def test_03_duplicate_batch_applied_once(self):
        b = {'batch': 'dup-test-1', 'from': 0, 'to': 10 ** 9, 'final': False,
             'items': [{'k': 'kaccha', 'rid': 'DUP-T', 'v': 10 ** 9, 'data': {'x': 1}}]}
        s1, r1 = req('POST', '/v1/sync/push', b, self.h())
        s2, r2 = req('POST', '/v1/sync/push', b, self.h())
        self.assertEqual((s1, s2), (200, 200))
        self.assertEqual(r1['applied'], 1)
        self.assertTrue(r2.get('repeat'), r2)
        with psycopg.connect(DSN) as c:
            n = c.execute("SELECT count(*) FROM records WHERE hotel_id = 'SYNTH1' AND k = 'kaccha' AND rid = 'DUP-T'").fetchone()[0]
            c.execute("DELETE FROM records WHERE hotel_id = 'SYNTH1' AND k = 'kaccha' AND rid = 'DUP-T'")
        self.assertEqual(n, 1)

    def test_04_older_data_never_overwrites_newer(self):
        st, ag = self.stores['SYNTH1'], self.agents['SYNTH1']
        r = self.settle('SYNTH1', 'order1', total=210)
        ag.sync_once()
        bid = r['bill']['id']
        with psycopg.connect(DSN) as c:
            v_new, tot = c.execute("SELECT src_version, total_p FROM bills WHERE hotel_id = 'SYNTH1' AND id = %s", (bid,)).fetchone()
        old = dict(r['bill'], total=1)
        s, j = req('POST', '/v1/sync/push', {'batch': 'stale-1', 'from': 0, 'to': v_new - 1, 'final': False,
                                              'items': [{'k': 'bills', 'rid': bid, 'v': v_new - 1, 'ord': 1, 'data': old}]}, self.h())
        self.assertEqual(s, 200, j)
        self.assertEqual(j['skipped'], 1)
        # A counter that lost its cursor sends everything again: nothing changes in the cloud
        with st.sdb.tx() as c:
            c.execute("DELETE FROM meta WHERE k = ?", (CC.CURSOR,))
        ag.sync_once()
        with psycopg.connect(DSN) as c:
            v2, tot2 = c.execute("SELECT src_version, total_p FROM bills WHERE hotel_id = 'SYNTH1' AND id = %s", (bid,)).fetchone()
        self.assertEqual((v2, tot2), (v_new, tot))
        self.assertEqual(tot2, 21000)
        self.assertCloudEqualsCounter('SYNTH1')

    def test_05_cancel_and_record_removal_reach_the_cloud(self):
        st = self.stores['SYNTH1']
        r = self.settle('SYNTH1', 'cancel1')
        with st.lock:
            code, j = st.apply_ops({'bv': st.version, 'ops': [{'k': 'bills', 'up': [dict(r['bill'], cancelled=True, cancelledBy='Manager')]},
                                                             {'k': 'kaccha', 'mset': {'T-9': {'items': []}}}]}, 'local')
        self.assertEqual(code, 200, j)
        self.assertCloudEqualsCounter('SYNTH1')
        with st.lock:
            code, j = st.apply_ops({'bv': st.version, 'ops': [{'k': 'kaccha', 'mdel': ['T-9']}]}, 'local')
        self.assertEqual(code, 200, j)
        self.assertCloudEqualsCounter('SYNTH1')
        # a whole-value save from the server (write) of a record list: the cloud follows it exactly
        with st.lock:
            stock = copy.deepcopy(st.data()['stock'])[:-1]
            st.write({'stock': stock})
        self.assertCloudEqualsCounter('SYNTH1')

    def test_06_same_bill_number_from_another_copy_is_stored_and_reported(self):
        st = self.stores['SYNTH1']
        self.assertCloudEqualsCounter('SYNTH1')
        with psycopg.connect(DSN) as c:
            no, = c.execute("SELECT no FROM bills WHERE hotel_id = 'SYNTH1' AND NOT imported AND NOT deleted AND no IS NOT NULL LIMIT 1").fetchone()
            n0 = c.execute("SELECT count(*) FROM conflicts WHERE hotel_id = 'SYNTH1'").fetchone()[0]
        other = dict(bill('foreign-1', 999), no=no, idemKey='foreign-idem')
        s, j = req('POST', '/v1/sync/push', {'batch': 'foreign-1', 'from': 0, 'to': st.version, 'final': False,
                                              'items': [{'k': 'bills', 'rid': 'p3-foreign-1', 'v': st.version, 'ord': 10 ** 9, 'data': other}]}, self.h())
        self.assertEqual(s, 200, j)
        self.assertEqual((j['applied'], j['conflicts']), (1, 1))
        s, j = admin('GET', '/v1/admin/conflicts?hotel=SYNTH1')
        self.assertEqual(len(j['conflicts']), n0 + 1)
        self.assertIn('same bill number', j['conflicts'][0]['reason'])
        self.assertEqual(j['conflicts'][0]['incoming']['total'], 999)
        with psycopg.connect(DSN) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM bills WHERE hotel_id = 'SYNTH1' AND id = 'p3-foreign-1' AND NOT deleted").fetchone()[0], 1)
        # The counter does not have that bill: its next full copy removes it from the replica (the report stays)
        with st.sdb.tx() as c:
            c.execute("DELETE FROM meta WHERE k = ?", (CC.CURSOR,))
        self.assertCloudEqualsCounter('SYNTH1')

    # ---------------------------------------------------------------- 4. tenant isolation
    def test_07_tenant_isolation_api(self):
        self.agents['SYNTH2'].sync_once()
        # B's key presented as A
        s, j = req('POST', '/v1/sync/push', {'batch': 'x', 'items': []}, {'X-Setu-Hotel': 'SYNTH1', 'X-Setu-Key': self.keys['SYNTH2']})
        self.assertEqual(s, 403)
        s, _ = req('GET', '/v1/sync/export', None, {'X-Setu-Hotel': 'SYNTH1', 'X-Setu-Key': 'sk_wrong'})
        self.assertEqual(s, 403)
        s, _ = req('GET', '/v1/sync/export', None, {})
        self.assertEqual(s, 401)
        # B's export never contains A's records
        db = cloud_doc('SYNTH2', self.keys['SYNTH2'])['data']
        self.assertEqual(db['settings']['hotelId'], 'SYNTH2')
        self.assertFalse([b for b in db['bills'] if 'SYNTH1' in str(b.get('idemKey'))])
        # Owner of A cannot read B's bill
        s, j = req('POST', '/v1/owner/login', {'hotel': 'SYNTH1', 'password': OWNER_PW})
        self.assertEqual(s, 200, j)
        tok = j['token']
        bid = next(b['id'] for b in db['bills'] if not b.get('imported'))
        s, _ = req('GET', f'/v1/owner/bill?id={bid}', None, {'X-Owner-Token': tok})
        self.assertEqual(s, 404 if bid not in {b['id'] for b in cloud_doc('SYNTH1', self.keys['SYNTH1'])['data']['bills']} else 200)
        s, j = req('GET', '/v1/owner/summary', None, {'X-Owner-Token': tok})
        self.assertEqual(j['hotel'], 'SYNTH1')
        # Admin commands go only to their hotel
        admin('POST', '/v1/admin/command', {'hotel': 'SYNTH2', 'kind': 'vendor_message', 'payload': {'text': 'Only for hotel two'}})
        s, j = req('GET', '/v1/sync/commands', None, self.h('SYNTH1'))
        self.assertFalse([c for c in j['commands'] if c['payload'].get('text') == 'Only for hotel two'])
        self.agents['SYNTH2'].sync_once()

    def test_08_tenant_isolation_sql_row_level_security(self):
        self.agents['SYNTH2'].sync_once()
        with psycopg.connect(DSN) as c:
            c.execute('SET ROLE setu_app')
            c.execute("SELECT set_config('setu.hotel', 'SYNTH1', false)")
            seen = {}
            for t in TABLES[:-1]:
                seen[t] = c.execute(f"SELECT count(*) FROM {t} WHERE hotel_id <> 'SYNTH1'").fetchone()[0]
            self.assertEqual(sum(seen.values()), 0, seen)
            self.assertGreater(c.execute('SELECT count(*) FROM bills').fetchone()[0], 0)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                c.execute("INSERT INTO records (hotel_id, k, rid, src_version, data) VALUES ('SYNTH2', 'x', 'y', 1, '{}')")
            c.rollback()
            c.execute('SET ROLE setu_app')
            c.execute("SELECT set_config('setu.hotel', '', false)")
            self.assertEqual(c.execute('SELECT count(*) FROM bills').fetchone()[0], 0, 'no hotel set: no rows')
            self.assertEqual(c.execute("UPDATE bills SET total_p = 0 WHERE hotel_id = 'SYNTH2'").rowcount, 0)
            c.rollback()

    # ---------------------------------------------------------------- 5. Super Admin commands
    def test_09_licence_message_lock_reach_counter_exactly_once(self):
        st, ag = self.stores['SYNTH1'], self.agents['SYNTH1']
        ag.sync_once()
        key = 'SETU-' + 'ABCDEFGHJKMNPQRSTUVWXYZ234567' * 5
        for kind, p in (('licence_key', {'key': key}), ('vendor_message', {'text': 'Your renewal is due on 30 November.'}),
                        ('vendor_lock', {'lv': 1, 'msg': 'Payment is due. Please contact Aghanya Devanya Enterprises.'})):
            s, j = admin('POST', '/v1/admin/command', {'hotel': 'SYNTH1', 'kind': kind, 'payload': p})
            self.assertEqual(s, 200, j)
        s, j = admin('POST', '/v1/admin/command', {'hotel': 'SYNTH1', 'kind': 'licence_key', 'payload': {'key': 'NOT-A-KEY'}})
        self.assertEqual(s, 400)
        s, j = admin('POST', '/v1/admin/command', {'hotel': 'SYNTH1', 'kind': 'delete_bills', 'payload': {}})
        self.assertEqual(s, 400, 'only the three command kinds exist')
        ag.sync_once()
        d = st.data()
        self.assertEqual(d['subscription']['cloudKeys'].count(key), 1)
        self.assertEqual(d['saas']['notice']['t'], 'Your renewal is due on 30 November.')
        self.assertEqual(d['saas']['lock']['lv'], 1)
        s, j = admin('GET', '/v1/admin/commands?hotel=SYNTH1')
        mine = [c for c in j['commands'] if c['kind'] in ('licence_key', 'vendor_message', 'vendor_lock')][:3]
        self.assertTrue(all(c['ackedAt'] and c['result']['ok'] for c in mine), mine)
        # the same key sent again (Super Admin pressed twice) is not added twice; lock off clears the lock
        admin('POST', '/v1/admin/command', {'hotel': 'SYNTH1', 'kind': 'licence_key', 'payload': {'key': key}})
        admin('POST', '/v1/admin/command', {'hotel': 'SYNTH1', 'kind': 'vendor_lock', 'payload': {'lv': 0}})
        ag.sync_once()
        st2 = self.stores['SYNTH1']
        self.assertEqual(st2.data()['subscription']['cloudKeys'].count(key), 1)
        self.assertIsNone(st2.data()['saas']['lock'])
        # survives a restart, and the cloud copy has it (pushed after applying)
        st.sdb.close()
        self.stores['SYNTH1'] = st = A.SqliteSetuStore(self.dirs['SYNTH1'])
        self.agents['SYNTH1'] = ag2 = CC.CloudAgent(st, ag.conf, interval=0.2)
        self.assertEqual(st.data()['saas']['notice']['t'], 'Your renewal is due on 30 November.')
        self.assertCloudEqualsCounter('SYNTH1')
        self.assertEqual(ag2.pull_commands(), 0, 'nothing is applied twice')

    # ---------------------------------------------------------------- 6. owner remote access
    def test_10_owner_login_read_only_and_rate_limited(self):
        self.assertCloudEqualsCounter('SYNTH1')
        s, j = req('POST', '/v1/owner/login', {'hotel': 'SYNTH1', 'password': OWNER_PW})
        self.assertEqual(s, 200, j)
        tok = j['token']
        s, summ = req('GET', '/v1/owner/summary', None, {'X-Owner-Token': tok})
        local = self.stores['SYNTH1'].sdb.export_document()
        want = sum(S.MONEY(b['total']) for b in local['bills'] if not b.get('cancelled') and isinstance(b.get('total'), (int, float)))
        self.assertEqual(summ['sales_p'], want, 'owner sales total equals the counter (paise)')
        s, j = req('GET', '/v1/owner/bills?date=2026-01-28', None, {'X-Owner-Token': tok})
        self.assertTrue(j['rows'])
        s, j = req('GET', f'/v1/owner/bill?id={j["rows"][0]["id"]}', None, {'X-Owner-Token': tok})
        self.assertEqual(s, 200)
        self.assertNotIn('secure', json.dumps(summ))
        # no write paths for the owner token
        s, _ = req('POST', '/v1/sync/push', {'batch': 'o', 'items': []}, {'X-Owner-Token': tok})
        self.assertEqual(s, 401)
        s, _ = req('POST', '/v1/admin/command', {'hotel': 'SYNTH1', 'kind': 'vendor_lock', 'payload': {'lv': 2}}, {'X-Owner-Token': tok})
        self.assertEqual(s, 401)
        # wrong password: refused, then rate limited (5 tries / 15 min)
        codes = [req('POST', '/v1/owner/login', {'hotel': 'SYNTH2', 'password': 'wrong'})[0] for _ in range(7)]
        self.assertEqual(codes[:5], [401] * 5)
        self.assertEqual(codes[5:], [429, 429])
        s, _ = req('POST', '/v1/owner/login', {'hotel': 'SYNTH2', 'password': OWNER_PW})
        self.assertEqual(s, 429, 'even the right password waits after too many wrong tries')
        req('POST', '/v1/owner/logout', {}, {'X-Owner-Token': tok})
        s, _ = req('GET', '/v1/owner/summary', None, {'X-Owner-Token': tok})
        self.assertEqual(s, 401)

    # ---------------------------------------------------------------- 7. QR orders
    def test_11_qr_order_flow(self):
        ag = self.agents['SYNTH1']
        self.assertCloudEqualsCounter('SYNTH1')
        code, j = ag.qr('POST', '/v1/qr/table', {'table': 'T-2', 'action': 'new'})
        self.assertEqual(code, 200, j)
        tok = j['tables']['T-2']['token']
        s, menu = req('GET', f'/v1/guest/menu?t={tok}')
        self.assertEqual(s, 200, menu)
        self.assertEqual(menu['table'], 'T-2')
        m1 = next(m for m in menu['items'] if m['id'] == 'm1')
        s, o = req('POST', '/v1/guest/order', {'t': tok, 'id': 'guestorder01', 'items': [{'mid': 'm1', 'qty': 2, 'price': 1}]})
        self.assertEqual(s, 200, o)
        s, again = req('POST', '/v1/guest/order', {'t': tok, 'id': 'guestorder01', 'items': [{'mid': 'm1', 'qty': 9}]})
        self.assertTrue(again.get('again'), 'a repeated order (network retry) is not a second order')
        code, state = ag.qr('GET', '/v1/qr/state')
        mine = [x for x in state['orders'] if x['id'] == o['id']]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]['items'][0]['price'], m1['price'], 'price comes from the menu, never the guest')
        self.assertEqual(mine[0]['items'][0]['qty'], 2)
        # first decision wins
        r1 = ag.qr('POST', '/v1/qr/decide', {'id': o['id'], 'action': 'accept', 'by': 'Waiter 1'})
        r2 = ag.qr('POST', '/v1/qr/decide', {'id': o['id'], 'action': 'reject', 'by': 'Waiter 2'})
        self.assertEqual((r1[0], r2[0]), (200, 409))
        # another hotel cannot decide or see it
        a2 = self.agents['SYNTH2']
        self.assertEqual(a2.qr('POST', '/v1/qr/decide', {'id': o['id'], 'action': 'reject'})[0], 404)
        self.assertFalse([x for x in a2.qr('GET', '/v1/qr/state')[1]['orders'] if x['id'] == o['id']])
        # the order reaches the counter's KOT through the counter's own save, then is marked done
        st = self.stores['SYNTH1']
        kot = {'id': 'kqr1', 'no': 99, 'date': '2026-01-28', 'items': r1[1]['order']['items'], 'status': 'new', 'table': 'T-2', 'qr': o['id']}
        with st.lock:
            code, j = st.apply_ops({'bv': st.version, 'ops': [{'k': 'kots', 'up': [kot]}]}, 'local')
        self.assertEqual(code, 200, j)
        self.assertEqual(ag.qr('POST', '/v1/qr/applied', {'id': o['id'], 'kot': '99'})[0], 200)
        self.assertEqual(next(x for x in ag.qr('GET', '/v1/qr/state')[1]['orders'] if x['id'] == o['id'])['status'], 'done')
        self.assertCloudEqualsCounter('SYNTH1')
        # flood limit: 5 pending per table
        codes = [req('POST', '/v1/guest/order', {'t': tok, 'id': f'flood{i:05d}', 'items': [{'mid': 'm1', 'qty': 1}]})[0] for i in range(6)]
        self.assertEqual(codes, [200] * 5 + [429])
        # switched-off table: refused
        ag.qr('POST', '/v1/qr/table', {'table': 'T-2', 'action': 'off'})
        self.assertEqual(req('GET', f'/v1/guest/menu?t={tok}')[0], 410)
        self.assertEqual(req('GET', '/v1/guest/menu?t=' + 'f' * 32)[0], 410)

    # ---------------------------------------------------------------- 8. backup and recovery
    def test_12_cloud_backup_verified_and_damage_detected(self):
        self.assertCloudEqualsCounter('SYNTH1')
        s, b = admin('POST', '/v1/admin/backup', {'hotel': 'SYNTH1'})
        self.assertEqual(s, 200, b)
        self.assertTrue(b['verified'])
        with gzip.open(b['file'], 'rt') as g:
            self.assertEqual(S.canonical_hash(json.load(g)), S.canonical_hash(self.stores['SYNTH1'].sdb.export_document()))
        self.assertTrue(admin('POST', '/v1/admin/backup/verify', {'hotel': 'SYNTH1', 'id': b['id']})[1]['ok'])
        raw = bytearray(open(b['file'], 'rb').read())
        raw[len(raw) // 2] ^= 0xFF
        open(b['file'], 'wb').write(bytes(raw))
        v = admin('POST', '/v1/admin/backup/verify', {'hotel': 'SYNTH1', 'id': b['id']})[1]
        self.assertFalse(v['ok'])
        self.assertIn('checksum', v['error'])
        self.assertEqual(admin('POST', '/v1/admin/backup/verify', {'hotel': 'SYNTH2', 'id': b['id']})[0], 404, 'another hotel cannot see the backup')
        RESULTS['backup'] = {'bytes': b['bytes'], 'bills': b['bills']}

    def test_13_counter_lost_recovered_from_cloud_identical(self):
        local = self.assertCloudEqualsCounter('SYNTH1')
        new = os.path.join(self.tmp, 'recovered')
        r = CC.recover(URL, 'SYNTH1', self.keys['SYNTH1'], new)
        st = A.SqliteSetuStore(new)
        try:
            self.assertEqual(S.canonical_hash(st.sdb.export_document()), S.canonical_hash(local))
            self.assertTrue(SEC.check_pin(st.data(), '739146'), 'manager PIN works after recovery')
            self.assertEqual(int(st.sdb.meta(CC.CURSOR)), r['version'])
            # the recovered counter continues: a new bill goes up incrementally
            ag = CC.CloudAgent(st, {'url': URL, 'hotel': 'SYNTH1', 'key': self.keys['SYNTH1']})
            code, j = st.settle_bill({'idemKey': 'after-recovery-1', 'bill': bill('after-rec-1')})
            self.assertEqual(code, 200, j)
            ag.sync_once()
            self.assertEqual(ag.state['snapshots'], 0)
            self.assertIn('after-recovery-1', {b.get('idemKey') for b in cloud_doc('SYNTH1', self.keys['SYNTH1'])['data']['bills']})
        finally:
            st.sdb.close()
        with self.assertRaises(CC.CloudError):
            CC.recover(URL, 'SYNTH1', self.keys['SYNTH1'], new)   # never over an existing database
        with self.assertRaises(CC.CloudError):
            CC.recover(URL, 'SYNTH1', self.keys['SYNTH2'], os.path.join(self.tmp, 'recovered-wrong'))
        # put the original counter back in step (the recovered one made a bill the original never saw)
        self.stores['SYNTH1'].sdb.close()
        shutil.rmtree(self.dirs['SYNTH1'])
        shutil.copytree(new, self.dirs['SYNTH1'])
        self.stores['SYNTH1'] = st = A.SqliteSetuStore(self.dirs['SYNTH1'])
        self.agents['SYNTH1'] = CC.CloudAgent(st, {'url': URL, 'hotel': 'SYNTH1', 'key': self.keys['SYNTH1']}, interval=0.2)

    # ---------------------------------------------------------------- 9. real counter server: crash, concurrent devices
    def _start_counter(self, d):
        env = dict(os.environ, SETU_CLOUD_URL=DEAD, SETU_CLOUD_INTERVAL='0.3', SETU_BACKUP='off')
        p = subprocess.Popen([sys.executable, os.path.join(ROOT, 'app_main.py'), '--server', '--port', str(SPORT), '--data', d],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        for _ in range(150):
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{SPORT}/api/ping', timeout=1)
                break
            except Exception:
                time.sleep(0.1)
        launch = open(os.path.join(d, 'setu-launch.key')).read().strip()
        s, j = req('POST', '/api/login', {'pin': '739146'}, {'X-Setu-Launch': launch}, url=f'http://127.0.0.1:{SPORT}')
        assert s == 200, j
        return p, {'X-Setu-Launch': launch, 'X-Setu-Token': j['token']}

    def _wait_synced(self, hdr, timeout=60):
        t = time.time()
        while time.time() - t < timeout:
            s, j = req('GET', '/api/cloud', None, hdr, url=f'http://127.0.0.1:{SPORT}')
            p3 = j.get('phase3') or {}
            if p3.get('pending') == 0 and p3.get('ok'):
                return p3
            time.sleep(0.3)
        raise AssertionError(f'counter did not finish syncing: {j}')

    def test_14_kill_9_during_sync_and_concurrent_devices(self):
        hid = 'SYNTH2'
        self.stores[hid].sdb.close()
        d = self.dirs[hid]
        with open(os.path.join(d, CC.CONF_FILE), 'w') as f:
            json.dump({'url': URL, 'hotel': hid, 'key': self.keys[hid]}, f)
        base = f'http://127.0.0.1:{SPORT}'
        p, hdr = self._start_counter(d)
        acked, stop = [], threading.Event()

        def device(w):
            i = 0
            while not stop.is_set():
                k = f'lan-{w}-{i}'
                try:
                    s, j = req('POST', '/api/bill/settle', {'idemKey': k, 'bill': bill(f'lan-{w}-{i}')}, hdr, url=base)
                    if s == 200:
                        acked.append(k)
                    if i % 3 == 0:   # a repeated request (device retry) never makes a second bill
                        s2, j2 = req('POST', '/api/bill/settle', {'idemKey': k, 'bill': bill(f'lan-{w}-{i}')}, hdr, url=base)
                        assert s2 == 200 and j2.get('alreadySettled'), (s2, j2)
                except Exception:
                    pass
                i += 1
        ts = [threading.Thread(target=device, args=(w,)) for w in range(8)]
        [t.start() for t in ts]
        time.sleep(4)
        p.kill()            # power cut while the agent is pushing and devices are billing
        p.wait()
        stop.set()
        [t.join() for t in ts]
        p, hdr = self._start_counter(d)
        try:
            # 8 devices again while the agent catches up
            stop.clear()
            ts = [threading.Thread(target=device, args=(w + 10,)) for w in range(8)]
            [t.start() for t in ts]
            time.sleep(3)
            stop.set()
            [t.join() for t in ts]
            st = self._wait_synced(hdr)
            RESULTS['concurrentDevices'] = {'devices': 8, 'acknowledgedBills': len(acked), 'agent': {k: st.get(k) for k in ('batches', 'pushed', 'bytesOut', 'snapshots', 'conflicts')}}
        finally:
            p.kill()
            p.wait()
        self.stores[hid] = A.SqliteSetuStore(d)
        local = self.stores[hid].sdb.export_document()
        have = {b.get('idemKey') for b in local['bills']}
        self.assertGreater(len(acked), 50)
        self.assertEqual([k for k in acked if k not in have], [], 'an acknowledged bill was lost')
        nos = [b['no'] for b in local['bills'] if not b.get('imported')]
        self.assertEqual(len(nos), len(set(nos)))
        cd = cloud_doc(hid, self.keys[hid])
        self.assertEqual(S.canonical_hash(cd['data']), S.canonical_hash(local), 'cloud equals counter after kill -9 and concurrent devices')
        self.assertEqual(st['conflicts'], 0)
        self.agents[hid] = CC.CloudAgent(self.stores[hid], {'url': URL, 'hotel': hid, 'key': self.keys[hid]})
        os.remove(os.path.join(d, CC.CONF_FILE))

    # ---------------------------------------------------------------- 10. measured costs
    def test_15_costs(self):
        st, ag = self.stores['SYNTH1'], self.agents['SYNTH1']
        ag.sync_once()
        lat, sizes = [], []
        for i in range(30):
            self.settle('SYNTH1', f'cost{i}')
            b0 = ag.state['bytesOut']
            t = time.perf_counter()
            ag.sync_once()
            lat.append((time.perf_counter() - t) * 1000)
            sizes.append(ag.state['bytesOut'] - b0)
        with psycopg.connect(DSN) as c:
            n = c.execute('SELECT count(*) FROM bills').fetchone()[0]
            tb = c.execute("SELECT pg_total_relation_size('bills')").fetchone()[0]
            rec = c.execute("SELECT pg_total_relation_size('records')").fetchone()[0]
            dbs = c.execute('SELECT pg_database_size(current_database())').fetchone()[0]
        RESULTS['costs'] = {'billsInCloud': n, 'billsTableBytes': tb, 'bytesPerBillTableAndIndexes': round(tb / max(n, 1)), 'recordsTableBytes': rec,
                            'databaseBytes': dbs, 'pushPerBillRequestBytesMedian': int(statistics.median(sizes)),
                            'pushLatencyMsMedian': round(statistics.median(lat), 1), 'pushLatencyMsP95': round(sorted(lat)[int(len(lat) * 0.95) - 1], 1),
                            'note': 'one settled bill per sync (worst case); localhost PostgreSQL 16, no network latency'}
        self.assertLess(statistics.median(sizes), 20000, 'a one-bill sync must not send whole documents')
        self.assertCloudEqualsCounter('SYNTH1')


if __name__ == '__main__':
    unittest.main(verbosity=2)
