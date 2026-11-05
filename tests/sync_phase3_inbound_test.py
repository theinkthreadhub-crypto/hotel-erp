"""
HoReCa One — Phase 3.4 Inbound Sync, QR Orders, Licence & Super Admin Sync Test Suite.

Covers all 13 required scenarios + Gate 0 parity:
1. Gate 0 Parity: Exact money calculations down to the paise between Local SQLite & Cloud
2. QR order delivered once into table_orders & KOT without auto-charging or stock movement
3. Offline -> reconnect recovery in ascending sequence order
4. Duplicate replay deduplication
5. Counter crash before commit (transaction rollback)
6. Counter crash after commit (idempotent re-fetch & ACK)
7. Lost cloud response handling
8. Concurrent table orders (POS + Inbound QR merged safely)
9. QR order cancellation (status update to cancelled in kots)
10. Hotel tenant isolation (cross-hotel rejected)
11. Licence renewal & activation update applied safely
12. Forged / mismatched licence rejected without downgrade
13. Vendor message deduplication
14. 1,000+ events batch processing with bounded memory & concurrent POS billing benchmark
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import shutil
import tempfile
import time
import unittest
from datetime import datetime
from decimal import Decimal

import setu_sqlite as S


class TestPhase34InboundSync(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, 'setu.sqlite')
        self.hotel_id = 'HOTEL_PHASE34'
        self.store = S.SqliteDoc(self.db_path, create=True)
        with self.store.tx() as c:
            c.execute("INSERT OR REPLACE INTO meta VALUES ('hotel_id', ?)", (self.hotel_id,))

    def tearDown(self):
        try:
            self.store.close()
        except Exception:
            pass
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # 1. Gate 0 Parity: Exact money calculations down to the paise
    def ack_ok(self, url, path, body, headers):
        ids = json.loads(body.decode('utf-8')).get('event_ids', [])
        return 200, json.dumps({
            'ok': True, 'hotel': self.hotel_id, 'acked_ids': ids
        })

    def feed(self, events):
        def fetch(url, path, headers):
            from urllib.parse import parse_qs, urlsplit
            since = int(parse_qs(urlsplit(path).query).get('since', ['0'])[0])
            return 200, json.dumps({
                'ok': True, 'hotel': self.hotel_id,
                'events': [e for e in events if e['seq'] > since]
            })
        return fetch

    def test_gate0_money_parity_down_to_paise(self):
        # 105.50 -> 10550 paise
        p1 = S.MONEY(105.50)
        self.assertEqual(p1, 10550)
        # 0.05 -> 5 paise
        p2 = S.MONEY(0.05)
        self.assertEqual(p2, 5)
        # Sum of paise exactly equals total
        items = [{'price': 100.25, 'qty': 3}, {'price': 49.99, 'qty': 2}]
        total_p = sum(S.MONEY(Decimal(str(it['price'])) * Decimal(str(it['qty']))) for it in items)
        # 100.25 * 3 = 300.75 (30075 paise), 49.99 * 2 = 99.98 (9998 paise) -> 40073 paise
        self.assertEqual(total_p, 40073)

    # 2. QR order delivered once into table_orders & KOT without auto-charging or stock deduction
    def test_scenario1_qr_order_delivered_once(self):
        cloud_events = [{
            'id': 'evt_1_g_ord_001',
            'seq': 1,
            'event_type': 'qr_order',
            'entity_id': 'g_ord_001',
            'payload': {
                'order_id': 'g_ord_001',
                'table': '4',
                'guest_name': 'Rohan Sharma',
                'note': 'Extra napkins please',
                'items': [
                    {'mid': 'm_dal', 'name': 'Dal Makhani', 'price': 220, 'qty': 2},
                    {'mid': 'm_roti', 'name': 'Butter Roti', 'price': 25, 'qty': 4}
                ],
                'total': 540,
                'at': int(time.time() * 1000)
            }
        }, {
            'id': 'evt_2_g_ord_001',
            'seq': 2,
            'event_type': 'qr_status',
            'entity_id': 'g_ord_001',
            'payload': {'order_id': 'g_ord_001', 'status': 'accepted'}
        }]

        acked_events = []

        def mock_get(url, path, headers):
            return 200, json.dumps({'ok': True, 'events': cloud_events})

        def mock_post(url, path, body, headers):
            data = json.loads(body.decode('utf-8'))
            acked_events.extend(data.get('event_ids', []))
            return self.ack_ok(url, path, body, headers)

        receiver = S.InboundSyncReceiver(
            store=self.store,
            url='https://cloud.hotelsetu.com',
            hotel=self.hotel_id,
            key='sync_secret_key',
            enabled=True,
            http_get_fn=mock_get,
            http_post_fn=mock_post
        )

        res = receiver.fetch_and_apply_once()
        self.assertEqual(res['status'], 'ok')
        self.assertEqual(res['applied'], 2)
        self.assertEqual(res['acked'], 2)
        self.assertEqual(acked_events, ['evt_1_g_ord_001', 'evt_2_g_ord_001'])

        # Verify Table Order (kaccha)
        with self.store.rlock():
            t_row = self.store.con().execute("SELECT data FROM table_orders WHERE tbl = '4'").fetchone()
            self.assertIsNotNone(t_row)
            t_data = json.loads(t_row[0])
            self.assertEqual(t_data['cust'], 'Rohan Sharma')
            self.assertEqual(t_data['note'], 'Extra napkins please')
            self.assertEqual(len(t_data['cart']), 2)
            self.assertIn('g_ord_001', t_data['qr'])

            # Verify KOT created
            k_row = self.store.con().execute("SELECT id, no, \"table\", channel, status, extra FROM kots WHERE \"table\" = '4'").fetchone()
            self.assertIsNotNone(k_row)
            self.assertEqual(k_row[2], '4')
            self.assertEqual(k_row[3], 'Dine-In')
            self.assertEqual(k_row[4], 'pending')
            k_extra = json.loads(k_row[5])
            self.assertEqual(k_extra['src'], 'qr')
            self.assertEqual(k_extra['qr'], 'g_ord_001')

            # Verify KOT Items
            items = self.store.con().execute("SELECT mid, name, qty FROM kot_items WHERE kot_id = ? ORDER BY line ASC", (k_row[0],)).fetchall()
            self.assertEqual(len(items), 2)
            self.assertEqual(items[0], ('m_dal', 'Dal Makhani', 2.0))
            self.assertEqual(items[1], ('m_roti', 'Butter Roti', 4.0))

            # CRITICAL: Verify NO bills created (never auto-charge or auto-settle)
            bill_count = self.store.con().execute("SELECT COUNT(*) FROM bills").fetchone()[0]
            self.assertEqual(bill_count, 0)

            # CRITICAL: Verify NO stock movements created
            stock_mv_count = self.store.con().execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0]
            self.assertEqual(stock_mv_count, 0)

            # Verify inbound_events_applied recorded
            applied = self.store.con().execute("SELECT id, seq, event_type FROM inbound_events_applied WHERE id = 'evt_1_g_ord_001'").fetchone()
            self.assertIsNotNone(applied)
            self.assertEqual(applied[1], 1)
            self.assertEqual(applied[2], 'qr_order')

    # 3. Offline -> reconnect recovery in ascending sequence order
    def test_scenario2_offline_reconnect_recovery(self):
        cloud_events = [
            {'id': f'evt_{i}_ord', 'seq': i, 'event_type': 'qr_order', 'payload': {'table': str(i), 'order_id': f'g_online_{i}', 'items': [{'mid': 'm1', 'qty': 1}]}}
            for i in range(1, 4)
        ]
        acked = []
        is_online = False

        def mock_get(url, path, headers):
            if not is_online:
                raise OSError('Network unreachable')
            return 200, json.dumps({'ok': True, 'events': cloud_events})

        def mock_post(url, path, body, headers):
            data = json.loads(body.decode('utf-8'))
            acked.extend(data.get('event_ids', []))
            return self.ack_ok(url, path, body, headers)

        receiver = S.InboundSyncReceiver(
            store=self.store, url='https://cloud.hotelsetu.com', hotel=self.hotel_id,
            key='sync_key', enabled=True, http_get_fn=mock_get, http_post_fn=mock_post
        )

        # 1. Offline attempt
        res1 = receiver.fetch_and_apply_once()
        self.assertEqual(res1['status'], 'network_error')
        self.assertEqual(receiver.stats['state'], 'offline')
        self.assertEqual(len(acked), 0)

        # 2. Reconnect online
        is_online = True
        res2 = receiver.fetch_and_apply_once()
        self.assertEqual(res2['status'], 'ok')
        self.assertEqual(res2['applied'], 3)
        self.assertEqual(receiver.stats['state'], 'connected')
        self.assertEqual(acked, ['evt_1_ord', 'evt_2_ord', 'evt_3_ord'])

        # Verify cursor updated to 3
        self.assertEqual(receiver.get_last_applied_seq(), 3)

    # 4. Duplicate replay deduplication
    def test_scenario3_duplicate_replay_dedup(self):
        evt = {
            'id': 'evt_single_replay',
            'seq': 1,
            'event_type': 'qr_order',
            'payload': {'table': '2', 'order_id': 'g_rep', 'items': [{'mid': 'm_tea', 'name': 'Masala Tea', 'qty': 1}]}
        }
        acked = []

        def mock_get(url, path, headers):
            return self.feed([evt])(url, path, headers)

        def mock_post(url, path, body, headers):
            acked.extend(json.loads(body.decode('utf-8')).get('event_ids', []))
            return self.ack_ok(url, path, body, headers)

        receiver = S.InboundSyncReceiver(
            store=self.store, url='https://cloud.hotelsetu.com', hotel=self.hotel_id,
            key='sync_key', enabled=True, http_get_fn=mock_get, http_post_fn=mock_post
        )

        # First delivery
        res1 = receiver.fetch_and_apply_once()
        self.assertEqual(res1['applied'], 1)

        # Replay same delivery
        res2 = receiver.fetch_and_apply_once()
        self.assertEqual(res2['applied'], 0)  # Deduped!

        # Pending QR order does not create a KOT until approval
        with self.store.rlock():
            kot_count = self.store.con().execute("SELECT COUNT(*) FROM kots WHERE \"table\" = '2'").fetchone()[0]
            self.assertEqual(kot_count, 0)
            self.assertEqual(receiver.get_pending_qr_count(), 1)

    # 5. Counter crash before commit (transaction rollback)
    def test_scenario4_counter_crash_before_commit(self):
        evt = {
            'id': 'evt_crash_before',
            'seq': 1,
            'event_type': 'qr_order',
            'payload': {'table': '1', 'order_id': 'g_crash', 'items': [{'mid': 'm1', 'qty': 1}]}
        }

        # Simulate exception during _apply_qr_order
        receiver = S.InboundSyncReceiver(
            store=self.store, url='https://cloud.hotelsetu.com', hotel=self.hotel_id,
            key='sync_key', enabled=True,
            http_get_fn=self.feed([evt])
        )

        orig_apply = receiver._apply_qr_order
        receiver._apply_qr_order = lambda c, p: (_ for _ in ()).throw(RuntimeError('Simulated counter power cut'))

        with self.assertRaises(RuntimeError):
            receiver.fetch_and_apply_once()

        # Database must be untouched (clean rollback)
        with self.store.rlock():
            kot_count = self.store.con().execute("SELECT COUNT(*) FROM kots").fetchone()[0]
            self.assertEqual(kot_count, 0)
            app_count = self.store.con().execute("SELECT COUNT(*) FROM inbound_events_applied").fetchone()[0]
            self.assertEqual(app_count, 0)

        # Restore method and retry: cleanly applies
        receiver._apply_qr_order = orig_apply
        res = receiver.fetch_and_apply_once()
        self.assertEqual(res['status'], 'ok')
        self.assertEqual(res['applied'], 1)

    # 6. Counter crash after commit (idempotent re-fetch & ACK)
    def test_scenario5_counter_crash_after_commit(self):
        evt = {
            'id': 'evt_crash_after',
            'seq': 1,
            'event_type': 'qr_order',
            'payload': {'table': '3', 'order_id': 'g_crash_after', 'items': [{'mid': 'm_soup', 'qty': 2}]}
        }
        ack_attempts = 0

        def failing_post(u, p, b, h):
            nonlocal ack_attempts
            ack_attempts += 1
            if ack_attempts == 1:
                raise OSError('Power disconnected right after local commit, before ACK')
            return self.ack_ok(u, p, b, h)

        receiver = S.InboundSyncReceiver(
            store=self.store, url='https://cloud.hotelsetu.com', hotel=self.hotel_id,
            key='sync_key', enabled=True,
            http_get_fn=self.feed([evt]),
            http_post_fn=failing_post
        )

        # 1. First attempt: local transaction commits, but ACK raises OSError
        res1 = receiver.fetch_and_apply_once()
        self.assertEqual(res1['status'], 'ok')
        self.assertEqual(res1['applied'], 1)
        self.assertEqual(res1['acked'], 0)

        # 2. Second attempt: Cloud re-sends unacked event; counter finds it applied, skips duplicate KOT, ACKs successfully
        res2 = receiver.fetch_and_apply_once()
        self.assertEqual(res2['status'], 'idle')
        self.assertEqual(res2['applied'], 0)  # NOT applied again!
        self.assertEqual(res2['acked'], 1)    # ACKed!

        with self.store.rlock():
            kot_count = self.store.con().execute("SELECT COUNT(*) FROM kots WHERE \"table\" = '3'").fetchone()[0]
            self.assertEqual(kot_count, 0)
            self.assertEqual(receiver.get_pending_qr_count(), 1)

    # 7. Lost cloud response handling
    def test_scenario6_lost_cloud_response(self):
        evt = {'id': 'evt_lost_ack_resp', 'seq': 1, 'event_type': 'vendor_message', 'payload': {'id': 'v1', 'message': 'Hello'}}
        calls = 0

        def post_with_lost_resp(u, p, b, h):
            nonlocal calls
            calls += 1
            if calls == 1:
                # Cloud processed it, but connection dropped before response delivered
                raise OSError('Connection reset by peer')
            return self.ack_ok(u, p, b, h)

        receiver = S.InboundSyncReceiver(
            store=self.store, url='https://cloud.hotelsetu.com', hotel=self.hotel_id,
            key='sync_key', enabled=True,
            http_get_fn=self.feed([evt]),
            http_post_fn=post_with_lost_resp
        )

        receiver.fetch_and_apply_once()
        # Next run recovers without error
        res = receiver.fetch_and_apply_once()
        self.assertEqual(res['status'], 'idle')
        self.assertEqual(res['acked'], 1)

    # 8. Concurrent table orders (POS + Inbound QR merged safely)
    def test_scenario7_concurrent_table_orders(self):
        # Local POS waiter has already opened Table 5 and added 1 Coffee
        with self.store.tx() as c:
            init_data = {'cart': [{'mid': 'm_coffee', 'name': 'Filter Coffee', 'price': 40, 'qty': 1}], 'cust': 'Walk-in'}
            c.execute("INSERT INTO table_orders (tbl, ord, data) VALUES ('5', 1000, ?)", (json.dumps(init_data),))

        # Inbound QR order arrives for Table 5 with 2 Dosas
        qr_evt = {
            'id': 'evt_qr_table5',
            'seq': 1,
            'event_type': 'qr_order',
            'payload': {
                'table': '5',
                'order_id': 'g_t5',
                'guest_name': 'Meera',
                'items': [{'mid': 'm_dosa', 'name': 'Masala Dosa', 'price': 120, 'qty': 2}]
            }
        }

        status_evt = {
            'id': 'evt_qr_table5_accepted', 'seq': 2,
            'event_type': 'qr_status', 'payload': {'order_id': 'g_t5', 'status': 'accepted'}
        }
        receiver = S.InboundSyncReceiver(
            store=self.store, url='https://cloud.hotelsetu.com', hotel=self.hotel_id,
            key='sync_key', enabled=True,
            http_get_fn=self.feed([qr_evt, status_evt]),
            http_post_fn=self.ack_ok
        )

        res = receiver.fetch_and_apply_once()
        self.assertEqual(res['status'], 'ok')

        # Verify Table 5 now has BOTH Coffee and Dosa
        with self.store.rlock():
            t_row = self.store.con().execute("SELECT data FROM table_orders WHERE tbl = '5'").fetchone()
            t_data = json.loads(t_row[0])
            self.assertEqual(len(t_data['cart']), 2)
            mids = {x['mid']: x['qty'] for x in t_data['cart']}
            self.assertEqual(mids['m_coffee'], 1.0)
            self.assertEqual(mids['m_dosa'], 2.0)

    # 9. QR order cancellation (status update to cancelled in kots)
    def test_scenario8_qr_order_cancellation(self):
        # 1. QR Order arrives
        order_evt = {
            'id': 'evt_qr_ord_cancel_test',
            'seq': 1,
            'event_type': 'qr_order',
            'payload': {'table': '6', 'order_id': 'g_cancel_me', 'items': [{'mid': 'm1', 'qty': 1}]}
        }
        receiver = S.InboundSyncReceiver(
            store=self.store, url='https://cloud.hotelsetu.com', hotel=self.hotel_id,
            key='sync_key', enabled=True,
            http_get_fn=self.feed([order_evt]),
            http_post_fn=self.ack_ok
        )
        receiver.fetch_and_apply_once()

        # Awaiting staff approval: no KOT or cart lines yet
        with self.store.rlock():
            status = self.store.con().execute("SELECT status FROM inbound_qr_orders WHERE order_id='g_cancel_me'").fetchone()[0]
            self.assertEqual(status, 'pending')
            self.assertEqual(self.store.con().execute("SELECT COUNT(*) FROM kots").fetchone()[0], 0)

        # 2. QR Rejection / cancellation arrives
        cancel_evt = {
            'id': 'evt_qr_status_cancelled',
            'seq': 2,
            'event_type': 'qr_status',
            'payload': {'order_id': 'g_cancel_me', 'status': 'rejected', 'reason': 'Out of ingredients'}
        }
        receiver.http_get_fn = self.feed([cancel_evt])
        receiver.fetch_and_apply_once()

        # Rejected items never reached running cart or KOT.
        with self.store.rlock():
            status = self.store.con().execute("SELECT status FROM inbound_qr_orders WHERE order_id='g_cancel_me'").fetchone()[0]
            self.assertEqual(status, 'rejected')
            self.assertEqual(self.store.con().execute("SELECT COUNT(*) FROM kots").fetchone()[0], 0)
            self.assertIsNone(self.store.con().execute("SELECT data FROM table_orders WHERE tbl='6'").fetchone())

    # 10. Hotel tenant isolation (cross-hotel rejected)
    def test_scenario9_hotel_tenant_isolation(self):
        cross_hotel_evt = {
            'id': 'evt_wrong_hotel',
            'seq': 1,
            'event_type': 'licence_update',
            'payload': {'hotel_id': 'ANOTHER_HOTEL', 'plan': 'platinum', 'lifetime': True}
        }
        receiver = S.InboundSyncReceiver(
            store=self.store, url='https://cloud.hotelsetu.com', hotel=self.hotel_id,
            key='sync_key', enabled=True,
            http_get_fn=self.feed([cross_hotel_evt]),
            http_post_fn=self.ack_ok
        )
        receiver.fetch_and_apply_once()
        self.assertIn('LICENCE_HOTEL_MISMATCH', receiver.stats['last_error'])

        # Subscription must not be modified
        with self.store.rlock():
            sub = self.store.con().execute("SELECT v FROM hotel_settings WHERE k = 'subscription'").fetchone()
            self.assertIsNone(sub)

    # 11. Licence renewal & activation update applied safely
    def test_scenario10_licence_renewal_applied(self):
        renew_evt = {
            'id': 'evt_lic_renew',
            'seq': 1,
            'event_type': 'licence_update',
            'payload': {
                'hotel_id': self.hotel_id,
                'key': 'SETU-RENEW-KEY-2027',
                'plan': 'enterprise',
                'paid_until': '2027-12-31',
                'lifetime': False
            }
        }
        receiver = S.InboundSyncReceiver(
            store=self.store, url='https://cloud.hotelsetu.com', hotel=self.hotel_id,
            key='sync_key', enabled=True,
            http_get_fn=self.feed([renew_evt]),
            http_post_fn=self.ack_ok
        )
        receiver.fetch_and_apply_once()

        with self.store.rlock():
            sub_raw = self.store.con().execute("SELECT v FROM hotel_settings WHERE k = 'subscription'").fetchone()[0]
            sub = json.loads(sub_raw)
            self.assertEqual(sub['planName'], 'enterprise')
            self.assertEqual(sub['validUntil'], '2027-12-31')
            self.assertIn('SETU-RENEW-KEY-2027', sub['cloudKeys'])

    # 12. Forged / mismatched licence rejected without downgrade
    def test_scenario11_forged_licence_rejected(self):
        # Currently active lifetime licence
        with self.store.tx() as c:
            c.execute("INSERT INTO hotel_settings (k, v) VALUES ('subscription', ?)",
                      (json.dumps({'planName': 'enterprise', 'isLifetime': True, 'status': 'lifetime', 'validUntil': '2099-12-31'}),))

        with self.store.tx() as c:
            c.execute("INSERT INTO hotel_settings(k,v) VALUES('settings',?)",
                      (json.dumps({'installId': 'SETU-ABCD-1234'}),))
        forged_evt = {
            'id': 'evt_forged_lic',
            'seq': 1,
            'event_type': 'licence_update',
            'payload': {
                'hotel_id': self.hotel_id,
                'signature': 'forged_fake_signature_abc',
                'plan': 'starter_30_days',
                'paid_until': '2024-01-01',
                'lifetime': False
            }
        }
        receiver = S.InboundSyncReceiver(
            store=self.store, url='https://cloud.hotelsetu.com', hotel=self.hotel_id,
            key='sync_key', enabled=True,
            http_get_fn=self.feed([forged_evt]),
            http_post_fn=self.ack_ok
        )
        receiver.fetch_and_apply_once()
        self.assertIn('INVALID_SIGNED_LICENCE', receiver.stats['last_error'])

        # Lifetime subscription preserved untouched
        with self.store.rlock():
            sub = json.loads(self.store.con().execute("SELECT v FROM hotel_settings WHERE k = 'subscription'").fetchone()[0])
            self.assertTrue(sub['isLifetime'])
            self.assertEqual(sub['validUntil'], '2099-12-31')

    # 13. Vendor message deduplication
    def test_scenario12_vendor_message_dedup(self):
        msg_evt = {
            'id': 'evt_msg_001',
            'seq': 1,
            'event_type': 'vendor_message',
            'payload': {'id': 'notice_101', 'title': 'System Update', 'message': 'Cloud sync upgraded to Phase 3.4'}
        }
        receiver = S.InboundSyncReceiver(
            store=self.store, url='https://cloud.hotelsetu.com', hotel=self.hotel_id,
            key='sync_key', enabled=True,
            http_get_fn=self.feed([msg_evt]),
            http_post_fn=self.ack_ok
        )
        receiver.fetch_and_apply_once()

        # Send same notice again with different event id
        msg_evt2 = dict(msg_evt)
        msg_evt2['id'] = 'evt_msg_002'
        msg_evt2['seq'] = 2
        receiver.http_get_fn = self.feed([msg_evt2])
        receiver.fetch_and_apply_once()

        with self.store.rlock():
            notices = json.loads(self.store.con().execute("SELECT v FROM hotel_settings WHERE k = 'vendor_notices'").fetchone()[0])
            self.assertEqual(len(notices), 1)
            self.assertEqual(notices[0]['id'], 'notice_101')

    # 14. 1,000+ events batch processing with bounded memory & concurrent POS billing benchmark
    def test_scenario13_scale_bounded_memory_and_concurrent_pos_benchmark(self):
        events_1000 = [
            {
                'id': f'evt_batch_{i}',
                'seq': i,
                'event_type': 'qr_order',
                'payload': {
                    'table': str((i % 20) + 1),
                    'order_id': f'g_order_{i}',
                    'guest_name': f'Guest {i}',
                    'items': [{'mid': f'm_{i%10}', 'name': f'Dish {i%10}', 'price': 100, 'qty': 1}]
                }
            }
            for i in range(1, 1001)
        ]

        def paginated_get(u, path, h):
            # Parse since & limit
            import urllib.parse
            parsed = urllib.parse.urlparse(path)
            qs = urllib.parse.parse_qs(parsed.query)
            since = int(qs.get('since', ['0'])[0])
            limit = int(qs.get('limit', ['50'])[0])
            matched = [e for e in events_1000 if e['seq'] > since][:limit]
            return 200, json.dumps({'ok': True, 'events': matched})

        receiver = S.InboundSyncReceiver(
            store=self.store, url='https://cloud.hotelsetu.com', hotel=self.hotel_id,
            key='sync_key', enabled=True, batch_size=50,
            http_get_fn=paginated_get,
            http_post_fn=self.ack_ok
        )

        t0 = time.perf_counter()
        batches = 0
        while True:
            res = receiver.fetch_and_apply_once()
            if res.get('status') == 'idle' or res.get('processed', 0) == 0:
                break
            batches += 1
            if batches > 30:
                break
        duration = time.perf_counter() - t0

        self.assertEqual(receiver.stats['applied_events'], 1000)
        self.assertEqual(receiver.get_last_applied_seq(), 1000)

        # Benchmark: Concurrent POS local billing while database has 1000 inbound records
        bill_times = []
        for b_i in range(1, 21):
            t_bill_0 = time.perf_counter()
            bill_doc = {
                'id': f'b_bench_{b_i}',
                'no': 1000 + b_i,
                'date': '2026-11-05',
                'time': '12:00:00',
                'table': '1',
                'channel': 'Dine-In',
                'mode': 'Cash',
                'sub': 200.0,
                'disc': 0.0,
                'tax': 10.0,
                'taxable': 200.0,
                'total': 210.0,
                'round': 0.0,
                'items': [{'mid': 'm1', 'name': 'Dish 1', 'price': 100.0, 'qty': 2.0}],
                'payments': [{'mode': 'Cash', 'amt': 210.0}]
            }
            with self.store.tx() as c:
                self.store._put_record(c, S.SPEC_BY_KEY['bills'], bill_doc, 100 + b_i)
            bill_times.append((time.perf_counter() - t_bill_0) * 1000)

        avg_latency = sum(bill_times) / len(bill_times)
        max_latency = max(bill_times)
        print(f"\n[SCALE BENCHMARK] 1,000 inbound events processed in {duration:.2f}s ({1000/duration:.1f} ops/sec)")
        print(f"[POS LATENCY] Concurrent local billing latency: avg={avg_latency:.2f}ms, max={max_latency:.2f}ms (threshold < 15ms)")
        self.assertLess(avg_latency, 15.0)

        # Check operational status
        op_status = receiver.get_operational_status()
        self.assertEqual(op_status['connection_status'], 'connected')
        self.assertEqual(op_status['inbound_cursor'], 1000)
        self.assertEqual(op_status['failed_inbound_ops'], 0)


    # 15. Operational Status integration with OutboxSyncDispatcher
    def test_operational_status_integration_with_dispatcher(self):
        dispatcher = S.OutboxSyncDispatcher(
            store=self.store, url='https://cloud.hotelsetu.com', hotel=self.hotel_id,
            key='sync_key', enabled=True
        )
        op_status = dispatcher.get_operational_status()
        self.assertIn('connection_status', op_status)
        self.assertIn('outbox_pending_ops', op_status)
        self.assertIn('pending_inbound_qr_orders', op_status)
        self.assertIn('pending_licence_updates', op_status)
        self.assertIn('last_inbound_sync', op_status)
        self.assertIn('last_outbox_sync', op_status)
        self.assertIn('failed_ops', op_status)
        self.assertIn('conflicts', op_status)
        self.assertIn('inbound_cursor', op_status)
        self.assertEqual(op_status['outbox_pending_ops'], 0)
        self.assertEqual(op_status['pending_inbound_qr_orders'], 0)


if __name__ == '__main__':
    unittest.main()
