import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import copy
import json
import shutil
import tempfile
import time
import unittest
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import setu_sqlite as SQ
import setu_migrate as M
from app_main import SqliteSetuStore


def sample_doc():
    return {
        'settings': {'name': 'Hotel Dispatcher Test', 'hotelId': 'TESTHOTEL01', 'appVersion': '3.2.0'},
        'auth': {'hotelId': 'TESTHOTEL01', 'ownerName': 'Test Owner'},
        'bills': [],
        'items': [{'id': 'm1', 'name': 'Tea', 'price': 20.0}],
        'vouchers': [],
        'stock': [],
        'stock_movements': [],
        'kots': [],
        'seq': {'bill': 0, 'kot': 0}
    }


def migrated(tmp, doc):
    d = os.path.join(tmp, 'hotel')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'setu-db.json'), 'w', encoding='utf-8') as f:
        json.dump({'version': 1, 'savedAt': 1, 'data': doc}, f, ensure_ascii=False)
    r = M.migrate(d, cutover=True)
    assert r['status'] == 'MIGRATED', r
    return d


def save_bill(store, bill, op_id=None):
    if not op_id:
        op_id = f"op_{bill['id']}"
    res, out = store.apply_ops({
        'ops': [{'k': 'bills', 'up': [bill]}],
        'bv': store.version,
        'id': op_id,
        'deviceId': 'counter-main'
    }, 'cashier')
    assert res == 200, f"apply_ops failed with {res}: {out}"
    return out


def save_voucher(store, voucher, op_id=None):
    if not op_id:
        op_id = f"op_{voucher['id']}"
    res, out = store.apply_ops({
        'ops': [{'k': 'vouchers', 'up': [voucher]}],
        'bv': store.version,
        'id': op_id,
        'deviceId': 'counter-main'
    }, 'cashier')
    assert res == 200, f"apply_ops failed with {res}: {out}"
    return out


class MockCloudServer(BaseHTTPRequestHandler):
    """
    Mock Cloud Ingestion Server that implements the Phase 3.1 POST /api/sync/ops contract.
    Supports fault injection: drop responses, return 500, simulate conflicts, etc.
    """
    def log_message(self, format, *args):
        pass  # Quiet logging

    def do_POST(self):
        content_len = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_len).decode('utf-8')
        try:
            req_data = json.loads(body or '{}')
        except Exception:
            req_data = {}

        hotel_header = self.headers.get('X-Setu-Hotel', '')
        sync_header = self.headers.get('X-Setu-Sync', '')

        # Fault injection hooks on server
        if getattr(self.server, 'simulate_timeout', False):
            time.sleep(1.5)

        if getattr(self.server, 'simulate_network_error', False):
            self.send_response(503)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error": "Service Unavailable"}')
            return

        if getattr(self.server, 'simulate_auth_fail', False) or sync_header != self.server.expected_sync_key:
            self.send_response(401)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error": "Invalid sync key"}')
            return

        if hotel_header != self.server.expected_hotel:
            self.send_response(403)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error": "HOTEL_TENANT_MISMATCH"}')
            return

        # Handle POST /api/sync/ops
        if self.path == '/api/sync/ops':
            batch = req_data.get('batch') or [req_data.get('envelope') or req_data]
            results = {}

            for env in batch:
                op_id = env.get('op_id')
                if not op_id:
                    continue

                # Verify checksum
                payload = env.get('payload') or {}
                calc_hash = SQ.hashlib.sha256(
                    json.dumps(SQ._normalize_numbers(payload), sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
                ).hexdigest()
                expected_hash = (env.get('integrity', {}).get('checksum') or '').replace('sha256:', '').lower()

                if calc_hash.lower() != expected_hash:
                    results[op_id] = {'status': 'rejected', 'error': 'INVALID_CHECKSUM'}
                    continue

                # Check for existing committed op_id
                existing = self.server.committed_inbox.get(op_id)
                if existing:
                    if existing['checksum'] == calc_hash:
                        # Idempotent replay
                        results[op_id] = {
                            'status': 'committed',
                            'duplicate': True,
                            'op_id': op_id,
                            'hotel_id': hotel_header or getattr(self.server, 'expected_hotel', 'TESTHOTEL01'),
                            'checksum': 'sha256:' + calc_hash,
                            'doc_version': env.get('doc_version'),
                            'at': existing['at']
                        }
                    else:
                        # Conflicting payload
                        self.server.conflicts_quarantine[op_id] = env
                        results[op_id] = {'status': 'rejected', 'error': 'CONFLICT_OP_ID_PAYLOAD_MISMATCH'}
                    continue

                # Check if injected conflict test
                if getattr(self.server, 'inject_conflict_for_op', None) == op_id:
                    self.server.conflicts_quarantine[op_id] = env
                    results[op_id] = {'status': 'rejected', 'error': 'CONFLICT_OP_ID_PAYLOAD_MISMATCH'}
                    continue

                # Commit operation
                now_ms = int(time.time() * 1000)
                self.server.committed_inbox[op_id] = {
                    'checksum': calc_hash,
                    'doc_version': env.get('doc_version'),
                    'at': now_ms,
                    'payload': payload
                }
                results[op_id] = {
                    'status': 'committed',
                    'op_id': op_id,
                    'hotel_id': hotel_header or getattr(self.server, 'expected_hotel', 'TESTHOTEL01'),
                    'checksum': 'sha256:' + calc_hash,
                    'doc_version': env.get('doc_version'),
                    'at': now_ms
                }

            # If simulate_lost_response_once is set: commit was done, but response is abruptly severed
            if getattr(self.server, 'simulate_lost_response_once', False):
                self.server.simulate_lost_response_once = False
                self.send_response(500)
                self.end_headers()
                return

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            resp = json.dumps({'ok': True, 'hotel': hotel_header, 'processed': len(batch), 'results': results})
            self.wfile.write(resp.encode('utf-8'))
            return

        self.send_response(404)
        self.end_headers()


class Phase32DispatcherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='setu_phase32_')
        self.doc = sample_doc()
        self.dir = migrated(self.tmp, self.doc)
        self.store = SqliteSetuStore(self.dir)

        # Start mock cloud HTTP server
        self.server = HTTPServer(('127.0.0.1', 0), MockCloudServer)
        self.port = self.server.server_address[1]
        self.cloud_url = f'http://127.0.0.1:{self.port}'
        self.server.expected_hotel = 'TESTHOTEL01'
        self.server.expected_sync_key = 'test_sync_key_phase32'
        self.server.committed_inbox = {}
        self.server.conflicts_quarantine = {}
        self.server.simulate_network_error = False
        self.server.simulate_auth_fail = False
        self.server.simulate_lost_response_once = False
        self.server.simulate_timeout = False

        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

    def tearDown(self):
        if getattr(self.store, 'dispatcher', None):
            self.store.dispatcher.stop(timeout=1.0)
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_offline_billing_followed_by_reconnect(self):
        """Cashier creates bills while offline; reconnect drains outbox cleanly."""
        # 1. Dispatcher is not yet active (offline mode)
        for i in range(1, 4):
            bill = {
                'id': f'b_offline_{i}',
                'no': i,
                'table': f'T-{i}',
                'channel': 'Dine-In',
                'mode': 'Cash',
                'total': 100.0 * i,
                'date': '2026-11-05',
                'items': [{'name': 'Chai', 'price': 20.0, 'qty': 5 * i, 'amount': 100.0 * i}],
                'pays': [{'mode': 'Cash', 'amt': 100.0 * i}]
            }
            save_bill(self.store, bill)

        pending = self.store.get_pending_outbox()
        self.assertEqual(len(pending), 3, "All 3 offline bills should be pending in outbox")

        # 2. Reconnect / activate dispatcher
        disp = self.store.start_cloud_sync(
            url=self.cloud_url,
            hotel='TESTHOTEL01',
            key='test_sync_key_phase32',
            enabled=True,
            poll_interval=0.05
        )

        # Wait for dispatcher to drain outbox
        timeout = time.time() + 4.0
        while time.time() < timeout:
            if len(self.store.get_pending_outbox()) == 0:
                break
            time.sleep(0.05)

        self.assertEqual(len(self.store.get_pending_outbox()), 0, "Outbox should be fully drained")
        self.assertEqual(len(self.server.committed_inbox), 3, "Cloud server should have committed all 3 bills")
        disp.stop()

    def test_02_cloud_acknowledgment_after_durable_commit(self):
        """Individual bill gets acknowledged only after cloud durability."""
        disp = SQ.OutboxSyncDispatcher(
            store=self.store,
            url=self.cloud_url,
            hotel='TESTHOTEL01',
            key='test_sync_key_phase32',
            enabled=True
        )

        bill = {'id': 'b_dur_1', 'no': 10, 'total': 250.0, 'date': '2026-11-05'}
        save_bill(self.store, bill)

        pending_before = self.store.get_pending_outbox()
        self.assertEqual(len(pending_before), 1)
        self.assertIsNone(pending_before[0]['sent_at'])

        # Dispatch single pass
        res = disp.dispatch_once()
        self.assertEqual(res['status'], 'ok')
        self.assertEqual(res['acked'], 1)

        pending_after = self.store.get_pending_outbox()
        self.assertEqual(len(pending_after), 0, "Should no longer be pending")

        # Inspect database row directly
        con = self.store.sdb.con()
        row = con.execute("SELECT sent_at FROM sync_outbox WHERE ref LIKE '%b_dur_1%'").fetchone()
        self.assertIsNotNone(row, "Row must exist in sync_outbox")
        self.assertIsNotNone(row[0], "sent_at must be populated with commit timestamp")

    def test_03_server_commits_but_response_lost_then_retry(self):
        """Cloud commits, network drops on return, counter retries and receives idempotent ack."""
        disp = SQ.OutboxSyncDispatcher(
            store=self.store,
            url=self.cloud_url,
            hotel='TESTHOTEL01',
            key='test_sync_key_phase32',
            enabled=True
        )

        bill = {'id': 'b_lost_resp', 'no': 11, 'total': 320.0, 'date': '2026-11-05'}
        save_bill(self.store, bill)

        # Server commits but return response fails (HTTP 500 simulate)
        self.server.simulate_lost_response_once = True
        res1 = disp.dispatch_once()
        self.assertEqual(res1['status'], 'server_error')

        # Bill must still be in pending outbox on counter!
        pending = self.store.get_pending_outbox()
        self.assertEqual(len(pending), 1)
        self.assertIn(pending[0]['payload']['op_id'], self.server.committed_inbox, "Cloud already committed it")

        # Second dispatch (retry with same op_id)
        res2 = disp.dispatch_once()
        self.assertEqual(res2['status'], 'ok')
        self.assertEqual(res2['acked'], 1)
        self.assertEqual(len(self.store.get_pending_outbox()), 0, "Outbox now acknowledged")

    def test_04_duplicate_replay_is_idempotent(self):
        """Replaying duplicate envelope returns committed status without duplication."""
        disp = SQ.OutboxSyncDispatcher(
            store=self.store,
            url=self.cloud_url,
            hotel='TESTHOTEL01',
            key='test_sync_key_phase32',
            enabled=True
        )

        bill = {'id': 'b_dup_rep', 'no': 12, 'total': 150.0, 'date': '2026-11-05'}
        save_bill(self.store, bill)

        res1 = disp.dispatch_once()
        self.assertEqual(res1['status'], 'ok')
        self.assertEqual(res1['acked'], 1)

        # Force un-ack locally to simulate replay
        with self.store.sdb.tx() as c:
            c.execute("UPDATE sync_outbox SET sent_at = NULL WHERE ref LIKE '%b_dup_rep%'")

        # Replay
        res2 = disp.dispatch_once()
        self.assertEqual(res2['status'], 'ok')
        self.assertEqual(res2['acked'], 1)
        self.assertEqual(len(self.server.committed_inbox), 1, "Cloud must still have only 1 record")

    def test_05_partial_batch_failure_and_individual_acknowledgments(self):
        """Batch with 1 good op and 1 corrupt op: good op is acknowledged, bad op remains."""
        disp = SQ.OutboxSyncDispatcher(
            store=self.store,
            url=self.cloud_url,
            hotel='TESTHOTEL01',
            key='test_sync_key_phase32',
            enabled=True
        )

        # Good bill
        bill1 = {'id': 'b_partial_good', 'no': 21, 'total': 180.0, 'date': '2026-11-05'}
        save_bill(self.store, bill1)

        # Manually insert an envelope with corrupted checksum
        corrupt_env = SQ.make_sync_envelope('op_corrupt_chk', 'TESTHOTEL01', 'counter', 99, int(time.time() * 1000), writes_rec={'bills': {'kind': 'rec', 'ups': [{'id': 'b_bad'}], 'rm': []}})
        corrupt_env['integrity']['checksum'] = 'sha256:0000000000000000000000000000000000000000000000000000000000000000'
        with self.store.sdb.tx() as c:
            SQ.SqliteDoc.append_outbox(c, 'ops', 'op_b_bad', 99, corrupt_env)

        pending = self.store.get_pending_outbox()
        self.assertEqual(len(pending), 2)

        res = disp.dispatch_once()
        self.assertEqual(res['status'], 'ok')
        self.assertEqual(res['acked'], 1)  # Only 1 committed

        # Good bill should be acked; bad bill should remain pending
        pending_after = self.store.get_pending_outbox()
        self.assertEqual(len(pending_after), 1)
        self.assertIn('b_bad', pending_after[0]['ref'])

    def test_06_counter_restart_with_pending_operations(self):
        """Simulate counter restart: pending operations persist and sync after reboot."""
        # 1. Create bills
        bill = {'id': 'b_reboot_1', 'no': 31, 'total': 400.0, 'date': '2026-11-05'}
        save_bill(self.store, bill)

        # 2. Simulate process termination and reboot by re-instantiating store
        rebooted_store = SqliteSetuStore(self.dir)
        pending = rebooted_store.get_pending_outbox()
        self.assertEqual(len(pending), 1)
        self.assertIn('b_reboot_1', pending[0]['ref'])

        # 3. New dispatcher starts on rebooted store
        disp = rebooted_store.start_cloud_sync(
            url=self.cloud_url,
            hotel='TESTHOTEL01',
            key='test_sync_key_phase32',
            enabled=True,
            poll_interval=0.05
        )

        timeout = time.time() + 3.0
        while time.time() < timeout:
            if len(rebooted_store.get_pending_outbox()) == 0:
                break
            time.sleep(0.05)

        self.assertEqual(len(rebooted_store.get_pending_outbox()), 0)
        disp.stop()

    def test_07_wrong_hotel_credentials_rejected(self):
        """Tenant mismatch is caught by activation safety and remote cloud."""
        # Configured for wrong hotel code
        disp = SQ.OutboxSyncDispatcher(
            store=self.store,
            url=self.cloud_url,
            hotel='WRONG_HOTEL_99',
            key='test_sync_key_phase32',
            enabled=True
        )

        safe, reason = disp.is_activation_safe()
        self.assertFalse(safe)
        self.assertIn('identity mismatch', reason.lower())

        # If forced directly, remote server rejects with 403
        disp.hotel = 'WRONG_HOTEL_99'
        disp.enabled = True
        disp.is_activation_safe = lambda: (True, 'OK')

        bill = {'id': 'b_wrong_tenant', 'no': 41, 'total': 50.0}
        save_bill(self.store, bill)

        res = disp.dispatch_once()
        self.assertEqual(res['status'], 'forbidden')
        self.assertEqual(res['http_code'], 403)
        self.assertEqual(len(self.store.get_pending_outbox()), 1, "Unacknowledged operation preserved safely")

    def test_08_conflicting_financial_payload_quarantined(self):
        """Payload conflict (409) is quarantined locally in sync_conflicts without data loss."""
        disp = SQ.OutboxSyncDispatcher(
            store=self.store,
            url=self.cloud_url,
            hotel='TESTHOTEL01',
            key='test_sync_key_phase32',
            enabled=True
        )

        bill = {'id': 'b_conflict_test', 'no': 51, 'total': 999.0}
        save_bill(self.store, bill)

        # Server injects a conflict on this op_id
        pending = self.store.get_pending_outbox()
        op_id = pending[0]['payload']['op_id']
        self.server.inject_conflict_for_op = op_id

        res = disp.dispatch_once()
        self.assertEqual(res['status'], 'ok')
        self.assertEqual(res['conflicts'], 1)
        self.assertEqual(res['acked'], 0)

        # Check local sync_conflicts table
        con = self.store.sdb.con()
        conflicts = con.execute("SELECT rid, reason FROM sync_conflicts WHERE rid = ?", (op_id,)).fetchall()
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0][1], 'CONFLICT_OP_ID_PAYLOAD_MISMATCH')

    def test_09_backlog_drained_in_bounded_batches(self):
        """Large backlog (60 ops) is dispatched in bounded batches (batch_size=20)."""
        # Create 60 items
        for i in range(1, 61):
            voucher = {'id': f'v_{i}', 'type': 'Expense', 'amount': float(i * 10), 'date': '2026-11-05'}
            save_voucher(self.store, voucher)

        self.assertEqual(len(self.store.get_pending_outbox(limit=100)), 60)

        disp = SQ.OutboxSyncDispatcher(
            store=self.store,
            url=self.cloud_url,
            hotel='TESTHOTEL01',
            key='test_sync_key_phase32',
            enabled=True,
            batch_size=20
        )

        # Pass 1: 20 processed
        r1 = disp.dispatch_once()
        self.assertEqual(r1['acked'], 20)
        self.assertEqual(len(self.store.get_pending_outbox(limit=100)), 40)

        # Pass 2: 20 processed
        r2 = disp.dispatch_once()
        self.assertEqual(r2['acked'], 20)
        self.assertEqual(len(self.store.get_pending_outbox(limit=100)), 20)

        # Pass 3: 20 processed
        r3 = disp.dispatch_once()
        self.assertEqual(r3['acked'], 20)
        self.assertEqual(len(self.store.get_pending_outbox(limit=100)), 0)

    def test_10_billing_remains_responsive_during_cloud_downtime(self):
        """Cashier billing latency remains under 25ms even when cloud is timing out / down."""
        # Cloud server is down / timing out
        self.server.simulate_timeout = True
        self.server.simulate_network_error = True

        disp = self.store.start_cloud_sync(
            url=self.cloud_url,
            hotel='TESTHOTEL01',
            key='test_sync_key_phase32',
            enabled=True,
            poll_interval=0.05
        )

        # Cashier creates 10 bills in a loop
        times = []
        for i in range(1, 11):
            t0 = time.perf_counter()
            bill = {
                'id': f'b_speed_{i}',
                'no': 100 + i,
                'total': 150.0,
                'date': '2026-11-05',
                'items': [{'name': 'Roti', 'price': 15.0, 'qty': 10}]
            }
            save_bill(self.store, bill)
            t1 = time.perf_counter()
            times.append((t1 - t0) * 1000)

        disp.stop()
        avg_ms = sum(times) / len(times)
        max_ms = max(times)
        print(f"\n[BENCHMARK] Local billing under cloud downtime: avg={avg_ms:.2f}ms, max={max_ms:.2f}ms")
        self.assertLess(avg_ms, 25.0, f"Average bill latency must be well under 25ms, got {avg_ms:.2f}ms")

    def test_11_conflict_quarantine_stops_continuous_retries(self):
        """Permanent conflict is quarantined (sent_at < 0) and not retried on next pass."""
        disp = SQ.OutboxSyncDispatcher(
            store=self.store,
            url=self.cloud_url,
            hotel='TESTHOTEL01',
            key='test_sync_key_phase32',
            enabled=True
        )

        bill = {'id': 'b_quar_test', 'no': 77, 'total': 300.0, 'date': '2026-11-05'}
        save_bill(self.store, bill, op_id='op_b_quar_test')

        # Inject conflict on server
        self.server.inject_conflict_for_op = 'op_b_quar_test'

        # Pass 1: Conflict returned, quarantined locally
        res1 = disp.dispatch_once()
        self.assertEqual(res1['conflicts'], 1)
        self.assertEqual(res1['acked'], 0)

        # Verify outbox row has negative sent_at (quarantined)
        with self.store.sdb.rlock():
            row = self.store.sdb.con().execute(
                "SELECT sent_at FROM sync_outbox WHERE ref LIKE '%b_quar_test%'"
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertLess(row[0], 0, "Quarantined op must have negative sent_at")

            # Verify sync_conflicts has 1 unresolved conflict
            conf_rows = self.store.sdb.con().execute(
                "SELECT rid, reason, resolved FROM sync_conflicts WHERE rid = 'op_b_quar_test'"
            ).fetchall()
            self.assertEqual(len(conf_rows), 1)
            self.assertEqual(conf_rows[0][2], 0, "Conflict must be unresolved (needs-review)")

        # Pass 2: Dispatcher runs again -> MUST NOT retry op_b_quar_test
        res2 = disp.dispatch_once()
        self.assertEqual(res2['status'], 'idle', "Quarantined op must not be re-selected for dispatch")
        self.assertEqual(res2['processed'], 0)

    def test_12_conflicted_dependency_blocks_subsequent_same_entity_ops(self):
        """Subsequent operations on the same entity as an unresolved conflict are held back."""
        disp = SQ.OutboxSyncDispatcher(
            store=self.store,
            url=self.cloud_url,
            hotel='TESTHOTEL01',
            key='test_sync_key_phase32',
            enabled=True
        )

        # 1. First bill op encounters a conflict
        bill1 = {'id': 'b_dep_1', 'no': 80, 'total': 100.0, 'date': '2026-11-05'}
        save_bill(self.store, bill1, op_id='op_b_dep_1')
        self.server.inject_conflict_for_op = 'op_b_dep_1'
        disp.dispatch_once()

        # Clear server injection so cloud is healthy again
        self.server.inject_conflict_for_op = None

        # 2. Second op updates the SAME bill (b_dep_1)
        bill1_update = {'id': 'b_dep_1', 'no': 80, 'total': 150.0, 'date': '2026-11-05'}
        save_bill(self.store, bill1_update, op_id='op_b_dep_1_update')

        # 3. Dispatch: The second op depends on b_dep_1 which has an unresolved conflict!
        # It must be held back, not bypassing the dependency!
        res = disp.dispatch_once()
        self.assertEqual(res['processed'], 0)
        self.assertNotIn('op_b_dep_1_update', self.server.committed_inbox, "Dependent op must NOT be committed while conflict active")

    def test_13_independent_ops_progress_past_quarantined_conflicts(self):
        """Independent operations on other entities proceed safely past active conflicts."""
        disp = SQ.OutboxSyncDispatcher(
            store=self.store,
            url=self.cloud_url,
            hotel='TESTHOTEL01',
            key='test_sync_key_phase32',
            enabled=True
        )

        # Conflicted bill b_ind_conf
        bill_conf = {'id': 'b_ind_conf', 'no': 91, 'total': 100.0, 'date': '2026-11-05'}
        save_bill(self.store, bill_conf, op_id='op_b_ind_conf')
        self.server.inject_conflict_for_op = 'op_b_ind_conf'
        disp.dispatch_once()
        self.server.inject_conflict_for_op = None

        # Independent bill b_ind_clean
        bill_clean = {'id': 'b_ind_clean', 'no': 92, 'total': 220.0, 'date': '2026-11-05'}
        save_bill(self.store, bill_clean, op_id='op_b_ind_clean')

        # Dispatch: Independent bill must be processed and acknowledged!
        res = disp.dispatch_once()
        self.assertEqual(res['acked'], 1)
        self.assertIn('op_b_ind_clean', self.server.committed_inbox)

    def test_14_mismatched_checksum_or_hotel_acknowledgment_treated_as_unconfirmed(self):
        """Cloud acknowledgment with wrong checksum or hotel ID is treated as unconfirmed."""
        disp = SQ.OutboxSyncDispatcher(
            store=self.store,
            url=self.cloud_url,
            hotel='TESTHOTEL01',
            key='test_sync_key_phase32',
            enabled=True
        )

        bill = {'id': 'b_mismatch_ack', 'no': 95, 'total': 310.0, 'date': '2026-11-05'}
        save_bill(self.store, bill, op_id='op_b_mismatch_ack')

        # Mock http post function that returns a corrupted/mismatched checksum in ack
        def corrupt_ack_http_post(url, path, body_bytes, headers, timeout=15):
            fake_resp = {
                'ok': True,
                'results': {
                    'op_b_mismatch_ack': {
                        'status': 'committed',
                        'op_id': 'op_b_mismatch_ack',
                        'hotel_id': 'TESTHOTEL01',
                        'checksum': 'sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff',
                        'doc_version': 10
                    }
                }
            }
            return 200, json.dumps(fake_resp)

        disp.http_post_fn = corrupt_ack_http_post
        res = disp.dispatch_once()
        self.assertEqual(res['acked'], 0, "Mismatched checksum ack must NOT be acknowledged")

        # Row remains pending
        with self.store.sdb.rlock():
            row = self.store.sdb.con().execute(
                "SELECT sent_at FROM sync_outbox WHERE ref LIKE '%b_mismatch_ack%'"
            ).fetchone()
            self.assertIsNone(row[0], "sent_at must remain NULL when checksum mismatches")

    def test_15_recovery_and_reconciliation_after_restart(self):
        """Full restart recovery: unacknowledged operations and conflicts persist and reconcile."""
        # 1. Create a bill and an expense voucher
        bill = {'id': 'b_reboot_1', 'no': 150, 'total': 450.0, 'date': '2026-11-05'}
        save_bill(self.store, bill, op_id='op_b_reboot_1')

        voucher = {'id': 'v_reboot_1', 'type': 'Expense', 'amount': 75.0, 'date': '2026-11-05'}
        save_voucher(self.store, voucher, op_id='op_v_reboot_1')

        # 2. Simulate counter reboot
        new_store = SqliteSetuStore(self.dir)
        new_disp = SQ.OutboxSyncDispatcher(
            store=new_store,
            url=self.cloud_url,
            hotel='TESTHOTEL01',
            key='test_sync_key_phase32',
            enabled=True
        )

        # 3. Pending operations are preserved
        pending = new_store.get_pending_outbox()
        self.assertEqual(len(pending), 2)

        # 4. Dispatch after reboot
        res = new_disp.dispatch_once()
        self.assertEqual(res['acked'], 2)
        self.assertIn('op_b_reboot_1', self.server.committed_inbox)
        self.assertIn('op_v_reboot_1', self.server.committed_inbox)

        # 5. Outbox now completely drained
        self.assertEqual(len(new_store.get_pending_outbox()), 0)

    def test_16_strict_acknowledgment_rejects_string_or_raw_seq_aliases(self):
        """Production ack_outbox strictly rejects string-only IDs, integers, or missing checksums."""
        bill = {'id': 'b_strict_ack', 'no': 201, 'total': 199.0, 'date': '2026-11-05'}
        save_bill(self.store, bill, op_id='op_b_strict_ack')

        pending = self.store.get_pending_outbox()
        target_item = [p for p in pending if p['ref'] == 'op_b_strict_ack'][0]
        seq = target_item['seq']
        p_obj = target_item['payload']

        # 1. Attempt string-only ack
        with self.store.sdb.tx() as write_con:
            r1 = self.store.sdb.ack_outbox(write_con, ['op_b_strict_ack'])
        self.assertEqual(r1, 0, "String-only ack must be rejected")

        # 2. Attempt raw sequence integer ack
        with self.store.sdb.tx() as write_con:
            r2 = self.store.sdb.ack_outbox(write_con, [seq])
        self.assertEqual(r2, 0, "Raw integer sequence ack must be rejected")

        # 3. Attempt dict with missing checksum
        with self.store.sdb.tx() as write_con:
            r3 = self.store.sdb.ack_outbox(write_con, [{'op_id': 'op_b_strict_ack', 'hotel_id': 'TESTHOTEL01'}])
        self.assertEqual(r3, 0, "Dict without checksum must be rejected")

        # Verify row is STILL pending
        row_pending = self.store.sdb.con().execute(
            "SELECT sent_at FROM sync_outbox WHERE seq = ?", (seq,)
        ).fetchone()
        self.assertIsNone(row_pending[0])

        # 4. Valid triple ack: (op_id, hotel_id, checksum) -> MUST SUCCEED
        valid_ack = {
            'op_id': p_obj['op_id'],
            'hotel_id': p_obj['hotel_id'],
            'checksum': p_obj['integrity']['checksum']
        }
        with self.store.sdb.tx() as write_con:
            r4 = self.store.sdb.ack_outbox(write_con, [valid_ack])
        self.assertEqual(r4, 1, "Exact triple ack must succeed")

        row_acked = self.store.sdb.con().execute(
            "SELECT sent_at FROM sync_outbox WHERE seq = ?", (seq,)
        ).fetchone()
        self.assertIsNotNone(row_acked[0])

    def test_17_exact_indexed_conflict_quarantine_prevents_false_matches(self):
        """Exact indexed conflict quarantine ensures similar substring op_ids are not quarantined."""
        disp = SQ.OutboxSyncDispatcher(
            store=self.store,
            url=self.cloud_url,
            hotel='TESTHOTEL01',
            key='test_sync_key_phase32',
            enabled=True
        )

        # Create two operations with overlapping names
        # Op 1: op_overlap
        # Op 2: op_overlap_longer_sub
        bill1 = {'id': 'b_ov_1', 'no': 211, 'total': 100.0, 'date': '2026-11-05'}
        save_bill(self.store, bill1, op_id='op_overlap')

        bill2 = {'id': 'b_ov_2', 'no': 212, 'total': 200.0, 'date': '2026-11-05'}
        save_bill(self.store, bill2, op_id='op_overlap_longer_sub')

        # Inject conflict ONLY for op_overlap
        self.server.inject_conflict_for_op = 'op_overlap'

        res = disp.dispatch_once()
        self.assertEqual(res['conflicts'], 1)
        self.assertEqual(res['acked'], 1)

        # op_overlap must be quarantined (sent_at < 0)
        with self.store.sdb.rlock():
            con = self.store.sdb.con()
            row1 = con.execute("SELECT sent_at FROM sync_outbox WHERE ref = 'op_overlap'").fetchone()
            row2 = con.execute("SELECT sent_at FROM sync_outbox WHERE ref = 'op_overlap_longer_sub'").fetchone()

        self.assertLess(row1[0], 0, "op_overlap must be quarantined with negative sent_at")
        self.assertGreater(row2[0], 0, "op_overlap_longer_sub must be successfully acknowledged (NOT quarantined)")


if __name__ == '__main__':
    unittest.main()
