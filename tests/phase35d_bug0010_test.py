"""Phase 3.5d hardening: BUG-0010 module policy, held-op recovery planning, TD-0011 e-mail key configuration.

Runs without the Worker (the real-Worker versions of these flows are in tests/phase35d_local_e2e.py test_07..test_10).
Synthetic data only.

    python tests/phase35d_bug0010_test.py
"""
import http.server
import json
import os
import re
import subprocess
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
os.environ.pop('RESEND_API_KEY', None)
import app_main as A                      # noqa: E402
import setu_sqlite as S                   # noqa: E402
from sqlite_phase2b_test import migrated  # noqa: E402
from sqlite_phase2_test import sample_doc  # noqa: E402


def bill(i):
    return {'id': f'u-{i}', 'table': '', 'channel': 'Takeaway', 'mode': 'Cash', 'items': [{'mid': 'm1', 'name': 'x', 'price': 100, 'qty': 1}],
            'sub': 100, 'tax': 5, 'total': 105, 'date': '2026-11-09', 'time': '12:00', 'used': []}


class Base(unittest.TestCase):
    def setUp(self):
        d = sample_doc(3)
        d['settings']['hotelId'] = d['auth']['hotelId'] = 'UNIT10'
        d['settings']['gupshupApiKey'] = 'synthetic-not-a-key'
        d['auth']['users'] = [{'id': 'u1', 'name': 'Owner', 'password': 'synthetic-pass', 'pinHash': 'pbkdf2$synthetic'}]
        self.tmp = tempfile.mkdtemp(prefix='horeca-bug0010-')
        self.dir = migrated(self.tmp, d)
        self.store = A.SqliteSetuStore(self.dir)

    def tearDown(self):
        self.store.sdb.close()

    def outbox(self):
        return [json.loads(r[0]) for r in self.store.sdb.con().execute('SELECT payload FROM sync_outbox ORDER BY seq')]

    def settle(self, i):
        code, r = self.store.settle_bill({'idemKey': f'u-idem-{i}', 'bill': bill(i)})
        self.assertEqual(code, 200, r)


class ModulePolicy(Base):
    def test_policy_mirrors_worker_whitelist(self):
        with open(os.path.join(ROOT, 'cloud', 'src', 'worker.js'), encoding='utf-8') as f:
            src = f.read()
        for section, name in (('records', 'RECORD'), ('maps', 'MAP'), ('values', 'VALUE')):
            m = re.search(rf"SUPPORTED_{name}_MODULES = new Set\(\[([^\]]*)\]\)", src)
            worker = set(re.findall(r"'([^']+)'", m.group(1)))
            self.assertEqual(worker, set(S.CLOUD_SYNC_MODULES[section]), f'{section}: counter policy and Worker whitelist drifted')
        self.assertFalse(set(S.LOCAL_ONLY_MODULES) & set().union(*S.CLOUD_SYNC_MODULES.values()), 'a key cannot be both')

    def test_first_bill_after_migration_has_no_local_or_secret_data(self):
        self.settle(0)
        env = self.outbox()[0]
        self.assertEqual(sorted(env['payload']['values']), ['auth', 'seq', 'settings'])
        self.assertIn('staff', env['sync_policy']['local_only'])
        wire = json.dumps(env).lower()
        for secret in ('synthetic-pass', 'pbkdf2$', 'synthetic-not-a-key', 'pinhash', '"password"', 'gupshupapikey'):
            self.assertNotIn(secret, wire, f'{secret} must never be in a cloud envelope')
        self.assertEqual(env['payload']['values']['auth']['users'], [{'id': 'u1', 'name': 'Owner'}], 'nested credentials removed')

    def test_menu_only_save_queues_nothing_and_keeps_data(self):
        self.settle(0)
        n = len(self.outbox())
        with self.store.lock:
            m = dict(self.store.data()['menu'][0], price=999)
            code, r = self.store.apply_ops({'bv': self.store.version, 'ops': [{'k': 'menu', 'up': [m]}]}, 'local')
        self.assertEqual(code, 200, r)
        self.assertEqual(len(self.outbox()), n)
        self.assertEqual(self.store.data()['menu'][0]['price'], 999)

    def test_unknown_module_is_kept_and_reported_every_time(self):
        for i in range(2):
            with self.store.lock:
                code, r = self.store.apply_ops({'bv': self.store.version, 'ops': [{'k': 'newThing', 'up': [{'id': f'n{i}'}]}]}, 'local')
            self.assertEqual(code, 200, r)
        self.assertEqual(len(self.store.data()['newThing']), 2)
        k, section, count, last_op, reason = self.store.sdb.con().execute(
            'SELECT k, section, count, last_op, reason FROM sync_unclassified').fetchone()
        self.assertEqual((k, section, count), ('newThing', 'records', 2))
        self.assertIn('setu_sqlite.py', reason)
        for env in self.outbox():
            self.assertNotIn('newThing', json.dumps(env['payload']), 'never sent to the cloud while unclassified')

    def test_cloud_module_in_wrong_section_is_reported(self):
        env = S.make_sync_envelope('x', 'UNIT10', 'd', 1, 1, writes_whole={'stock': [{'name': 'no id'}], 'seq': {'bill': 1}})
        self.assertEqual(env['integrity']['keys'], ['seq'])
        self.assertEqual(env['unclassified'], [{'k': 'stock', 'section': 'values'}])
        with self.store.sdb.tx() as c:
            S.SqliteDoc.enqueue_envelope(c, 'ops', env)
        reason = self.store.sdb.con().execute("SELECT reason FROM sync_unclassified WHERE k = 'stock'").fetchone()[0]
        self.assertIn('ingests it only as records', reason)


class HeldOpRecovery(Base):
    def hold_first_bill_like_the_outage_run(self):
        """Queues the first bill the way the pre-fix counter did (with values.staff) and holds it as the Worker would."""
        self.settle(0)
        env = self.outbox()[0]
        env['payload']['values']['staff'] = [{'id': 's1', 'name': 'Ravi', 'hasPin': False}]
        canon = json.dumps(env['payload'], sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        env['integrity']['checksum'] = 'sha256:' + __import__('hashlib').sha256(canon.encode()).hexdigest()
        with self.store.sdb.tx() as c:
            c.execute('UPDATE sync_outbox SET payload = ?, sent_at = -1 WHERE seq = (SELECT MIN(seq) FROM sync_outbox)', (json.dumps(env),))
            S.SqliteDoc.record_conflict(c, 'settle', env['op_id'], 'UNSUPPORTED_BUSINESS_MODULE', other=env)
        for i in range(1, 4):
            self.settle(i)
        return env

    def test_dry_run_changes_nothing_and_cli_needs_backup_flag(self):
        env = self.hold_first_bill_like_the_outage_run()
        con = self.store.sdb.con()
        snap = (con.execute('SELECT COUNT(*), SUM(seq) FROM sync_outbox').fetchone(), con.execute('SELECT COUNT(*) FROM sync_conflicts').fetchone())
        self.store.sdb.close()
        out = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'replay_held_ops.py'), '--data', self.dir],
                             capture_output=True, text=True, check=True)
        plan = json.loads(out.stdout)
        self.assertEqual([r['op_id'] for r in plan['replay']], [env['op_id']])
        self.assertEqual(plan['replay'][0]['bills'], ['u-0'])
        refused = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'replay_held_ops.py'), '--data', self.dir, '--apply'],
                                 capture_output=True, text=True)
        self.assertNotEqual(refused.returncode, 0, 'apply without --i-have-a-backup is refused')
        self.store = A.SqliteSetuStore(self.dir)
        con = self.store.sdb.con()
        self.assertEqual((con.execute('SELECT COUNT(*), SUM(seq) FROM sync_outbox').fetchone(), con.execute('SELECT COUNT(*) FROM sync_conflicts').fetchone()), snap)

    def test_apply_keeps_identity_history_and_is_idempotent(self):
        env = self.hold_first_bill_like_the_outage_run()
        plan = S.plan_held_op_replay(self.store.sdb)
        new = plan['replay'][0]['envelope']
        self.assertEqual((new['op_id'], new['hotel_id'], new['doc_version']), (env['op_id'], env['hotel_id'], env['doc_version']))
        self.assertEqual(sorted(new['payload']['values']), ['auth', 'settings'], 'seq superseded by later ops, staff local-only')
        self.assertEqual(new['payload']['records']['bills']['ups'][0]['total'], 105)
        self.assertEqual(new['replay_of']['original_checksum'], env['integrity']['checksum'])
        self.assertEqual(len(S.apply_held_op_replay(self.store.sdb, plan)), 1)
        self.assertEqual(S.apply_held_op_replay(self.store.sdb, plan), [], 'same plan twice: nothing new')
        again = S.plan_held_op_replay(self.store.sdb)
        self.assertEqual((again['replay'], len(again['already_replayed'])), ([], 1))
        con = self.store.sdb.con()
        self.assertEqual(con.execute('SELECT COUNT(*) FROM sync_outbox WHERE sent_at < 0').fetchone()[0], 1, 'held row untouched')
        self.assertEqual(con.execute("SELECT reason FROM sync_conflicts WHERE rid = ? ORDER BY seq", (env['op_id'],)).fetchall(),
                         [('UNSUPPORTED_BUSINESS_MODULE',), ('REPLAYED_CLOUD_PART (BUG-0010)',)])
        pend = self.store.get_pending_outbox(10)
        self.assertEqual([p['ref'] for p in pend if p['op'] == 'replay'], [env['op_id']])
        local = S.local_synced_bill_totals(self.store.sdb)
        self.assertEqual((local['bill_count'], local['gross_sales_p']), (4, 4 * 10500))

    def test_record_superseded_by_later_op_is_not_replayed(self):
        env = self.hold_first_bill_like_the_outage_run()
        later = S.make_sync_envelope('later', 'UNIT10', 'd', env['doc_version'] + 50, 1,
                                     writes_rec={'bills': ('spec', [dict(bill(0), cancelled=True)], [])})
        with self.store.sdb.tx() as c:
            S.SqliteDoc.enqueue_envelope(c, 'ops', later)
        item = S.plan_held_op_replay(self.store.sdb)['replay'][0]
        self.assertNotIn('bills', item['envelope']['payload']['records'], 'the later op carries the newer bill state')
        self.assertIn({'section': 'records', 'k': 'bills', 'why': '1 record(s) superseded by a later op'}, item['dropped'])


class EmailKeyConfiguration(Base):
    def test_no_literal_default_and_file_or_env_config(self):
        self.assertEqual(A.resend_api_key(), '')
        self.assertEqual(A.resend_api_key(self.dir), '')
        with open(os.path.join(self.dir, A.RESEND_KEY_FILE), 'w') as f:
            f.write('synthetic-config-value\n')
        self.assertEqual(A.resend_api_key(self.dir), 'synthetic-config-value')
        with self.assertRaises(A.EmailNotConfigured):
            A.send_resend_email('owner@example.com', 's', '<p>x</p>')

    def test_missing_key_fails_only_password_email_not_billing(self):
        srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), A.make_handler(ROOT, self.store, 0))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            req = urllib.request.Request(f'http://127.0.0.1:{srv.server_address[1]}/api/auth/forgot-password/send', method='POST',
                                         data=json.dumps({'email': 'owner@example.com', 'hotelId': 'UNIT10'}).encode(),
                                         headers={'Content-Type': 'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req, timeout=10)
            self.assertEqual(cm.exception.code, 503)
            self.assertIn('not set up', json.loads(cm.exception.read())['error'])
            self.assertEqual(self.store.reset_otps, {}, 'no OTP left waiting for an e-mail that was never sent')
        finally:
            srv.shutdown()
        self.settle(0)
        self.assertEqual(self.store.sdb.con().execute("SELECT COUNT(*) FROM bills WHERE id = 'u-0'").fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
