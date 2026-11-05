"""Phase 3.5: live counter-cache + LAN change-feed integration (synthetic only).

This test uses the real SqliteSetuStore wrapper, not just a SqliteDoc mock.
It never connects to production or sends live guest orders.
"""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))
import app_main as A
import setu_sqlite as S
from sqlite_phase2b_test import migrated
from sqlite_phase2_test import sample_doc


class CounterQrIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='horeca-p35-')
        self.prev_backup = os.environ.get('SETU_BACKUP')
        os.environ['SETU_BACKUP'] = 'off'
        path = migrated(self.tmp.name, sample_doc(3))
        self.data_dir = path
        self.counter = A.SqliteSetuStore(path)
        self.hotel = self.counter.hotel_id().upper()
        self.start_version = self.counter.version
        self.initial_outbox = self.counter.sdb.con().execute(
            "SELECT COUNT(*) FROM sync_outbox"
        ).fetchone()[0]
        self.events = []
        self.acked = []

    def tearDown(self):
        if self.counter.dispatcher:
            self.counter.stop_cloud_sync()
        self.counter.sdb.close()
        if self.prev_backup is None:
            os.environ.pop('SETU_BACKUP', None)
        else:
            os.environ['SETU_BACKUP'] = self.prev_backup
        self.tmp.cleanup()

    def feed(self, url, path, headers):
        from urllib.parse import urlsplit, parse_qs
        since = int(parse_qs(urlsplit(path).query).get('since', ['0'])[0])
        return 200, json.dumps({
            'ok': True, 'hotel': self.hotel,
            'events': [e for e in self.events if e['seq'] > since]
        })

    def ack(self, url, path, body, headers):
        payload = json.loads(body)
        if path == '/api/qr/applied':
            return 200, json.dumps({
                'ok': True, 'id': payload['id'], 'kot': payload['kot']
            })
        ids = payload['event_ids']
        self.acked.extend(ids)
        return 200, json.dumps({
            'ok': True, 'hotel': self.hotel, 'acked_ids': ids
        })

    def evt(self, event_type, payload):
        seq = len(self.events) + 1
        obj = {'id': f'evt_{seq}_int{seq}', 'seq': seq,
               'event_type': event_type, 'entity_id': payload.get('order_id'),
               'payload': payload}
        self.events.append(obj)
        return obj

    def receiver(self):
        return S.InboundSyncReceiver(
            store=self.counter, hotel=self.hotel, key='synthetic_local_key',
            url='https://test.invalid', enabled=True,
            http_get_fn=self.feed, http_post_fn=self.ack
        )

    def test_pending_approval_queue_does_not_modify_existing_cart(self):
        start_cart = self.counter.data().get('kaccha', {})
        self.evt('qr_order', {
            'order_id': 'g_int1', 'table': '7',
            'guest_name': 'Test Guest',
            'items': [{'mid':'m1', 'name':'Dish', 'qty': 2, 'price': 290}]
        })
        r = self.receiver()
        result = r.fetch_and_apply_once()
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['acked'], 1)
        self.assertEqual(self.counter.query('inbound-qr', {'status': 'pending'})['count'], 1)
        self.assertEqual(self.counter.data().get('kaccha', {}), start_cart)
        self.assertEqual(self.counter.version, self.start_version + 1)
        self.assertEqual(self.counter.bill_count(), 4)
        self.assertEqual(self.counter.sdb.con().execute(
            "SELECT COUNT(*) FROM sync_outbox").fetchone()[0], self.initial_outbox)

    def test_acceptance_updates_lan_change_feed_and_kot_items(self):
        self.evt('qr_order', {
            'order_id': 'g_int2', 'table': '8',
            'items': [{'mid':'m1','name':'Paneer','qty': 3, 'price': 290}]
        })
        self.evt('qr_status', {'order_id': 'g_int2', 'status': 'accepted'})
        r = self.receiver()
        result = r.fetch_and_apply_once()
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['applied'], 2)
        self.assertEqual(result['acked'], 2)
        self.assertEqual(self.counter.version, self.start_version + 2)
        self.assertEqual(self.counter.query('inbound-qr', {'status': 'accepted'})['count'], 1)
        ws = self.counter.data()
        self.assertIn('8', ws['kaccha'])
        self.assertEqual(ws['kaccha']['8']['cart'][0]['qty'], 3)
        qr_kots = [k for k in ws['kots'] if k.get('qr') == 'g_int2']
        self.assertEqual(len(qr_kots), 1)
        self.assertEqual(qr_kots[0]['items'][0]['qty'], 3)
        self.assertGreaterEqual(int(ws['seq']['kot']), int(qr_kots[0]['no']))
        changes = self.counter.changes(self.start_version)
        self.assertEqual(changes['version'], self.counter.version)
        by_key = {op['k']: op for op in changes.get('ops', [])}
        self.assertIn('kots', by_key)
        self.assertIn('kaccha', by_key)
        self.assertIn('seq', by_key)
        self.assertTrue(any(k.get('id') == qr_kots[0]['id'] for k in by_key['kots']['up']))
        self.assertEqual(self.counter.bill_count(), 4)
        self.assertEqual(self.counter.sdb.con().execute(
            "SELECT COUNT(*) FROM sync_outbox").fetchone()[0], self.initial_outbox)

    def test_qr_acceptance_marks_only_qr_dishes_sent_and_keeps_kds_clock(self):
        # Existing waiter order has two unsent dishes and one previously
        # KOT-issued dish. Accepted QR items must not reprint them.
        with self.counter.lock:
            status, result = self.counter.apply_ops({
                'bv': self.counter.version, 'id': 'pre_qr_waiter_sent_case',
                'ops': [{'k': 'kaccha', 'mset': {
                    '11': {
                        'table': '11',
                        'cart': [{'mid':'m0','name':'Waiter','qty':2,'price':120},
                                 {'mid':'m1','name':'Paneer','qty':1,'price':290}],
                        'sent': {'m0': 1},
                        'cust': 'Waiter'
                    }
                }}]}, 'local', True)
        self.assertEqual(status, 200, result)
        self.evt('qr_order', {
            'order_id':'g_sent11','table':'11',
            'items':[{'mid':'m0','name':'Waiter','qty':3,'price':120}]
        })
        self.evt('qr_status', {'order_id':'g_sent11','status':'accepted'})
        out=self.receiver().fetch_and_apply_once()
        self.assertEqual(out['status'],'ok',out)
        order=self.counter.data()['kaccha']['11']
        self.assertEqual(sum(i['qty'] for i in order['cart'] if i['mid']=='m0'),5)
        self.assertEqual(order['sent']['m0'],4)
        self.assertNotIn('m1',order['sent'])
        kot=[k for k in self.counter.data()['kots'] if k.get('qr')=='g_sent11'][0]
        self.assertIsInstance(kot['at'],int)
        self.assertGreater(kot['at'],0)
        self.assertEqual(kot['items'][0]['qty'],3)

    def test_rejection_preserves_waiter_cart_and_no_kitchen_ticket(self):
        with self.counter.lock:
            status, output = self.counter.apply_ops({
                'bv': self.counter.version, 'id': 'synthetic_waiter_cart',
                'ops': [{'k': 'kaccha', 'mset': {
                    '9': {'cart': [{'mid':'m0','qty':1,'price':120}], 'cust':'Waiter'}
                }}]}, 'local', True)
        self.assertEqual(status, 200, output)
        initial_kots = len(self.counter.data()['kots'])
        self.evt('qr_order', {
            'order_id':'g_reject9', 'table':'9',
            'items':[{'mid':'m0','qty':5, 'price':120}]
        })
        self.evt('qr_status', {'order_id':'g_reject9', 'status':'rejected'})
        result = self.receiver().fetch_and_apply_once()
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(len(self.counter.data()['kots']), initial_kots)
        self.assertEqual(
            self.counter.data()['kaccha']['9']['cart'],
            [{'mid':'m0','qty':1,'price':120}]
        )
        self.assertEqual(self.counter.query('inbound-qr', {'status':'rejected'})['count'], 1)

    def test_lost_cloud_kot_confirmation_retries_without_second_kot(self):
        self.evt('qr_order', {
            'order_id':'g_confirm_retry','table':'T3',
            'items':[{'mid':'m1','name':'Paneer','qty':1,'price':180}]
        })
        self.evt('qr_status', {
            'order_id':'g_confirm_retry','status':'accepted'
        })
        attempts=[]
        def lose_first_cloud_receipt(url,path,body,headers):
            if path == '/api/qr/applied':
                attempts.append(json.loads(body))
                if len(attempts)==1:
                    return 503, json.dumps({'ok':False,'error':'temporary outage'})
            return self.ack(url,path,body,headers)
        r=S.InboundSyncReceiver(
            store=self.counter, hotel=self.hotel, key='synthetic_local_key',
            url='https://test.invalid', enabled=True,
            http_get_fn=self.feed, http_post_fn=lose_first_cloud_receipt
        )
        result=r.fetch_and_apply_once()
        self.assertEqual(result['status'],'ok',result)
        self.assertEqual(result['applied'],2)
        with self.counter.sdb.rlock():
            row=self.counter.sdb.con().execute(
                "SELECT cloud_applied_at,kot_id FROM inbound_qr_orders WHERE order_id='g_confirm_retry'"
            ).fetchone()
            self.assertIsNone(row[0])
            self.assertIsNotNone(row[1])
        self.assertEqual(len(attempts),1)
        retry=r.fetch_and_apply_once()
        self.assertEqual(retry['status'],'idle',retry)
        self.assertEqual(len(attempts),2)
        self.assertEqual(attempts[0],attempts[1])
        with self.counter.sdb.rlock():
            self.assertIsNotNone(self.counter.sdb.con().execute(
                "SELECT cloud_applied_at FROM inbound_qr_orders WHERE order_id='g_confirm_retry'"
            ).fetchone()[0])
            self.assertEqual(self.counter.sdb.con().execute(
                "SELECT COUNT(*) FROM kots WHERE id=?", (row[1],)
            ).fetchone()[0],1)
        # A third poll cannot send a duplicate cloud receipt.
        self.assertEqual(r.fetch_and_apply_once()['status'],'idle')
        self.assertEqual(len(attempts),2)

    def test_restart_preserves_original_bills_and_accepted_qr_ticket(self):
        original_bills = self.counter.bill_count()
        original_stock = self.counter.data()['stock']
        self.evt('qr_order', {
            'order_id':'g_reboot', 'table':'10',
            'items':[{'mid':'m1','name':'Paneer','qty':2,'price':290}]
        })
        self.evt('qr_status', {'order_id':'g_reboot','status':'accepted'})
        self.assertEqual(self.receiver().fetch_and_apply_once()['status'],'ok')
        version = self.counter.version
        self.counter.sdb.close()
        self.counter = A.SqliteSetuStore(self.data_dir)
        self.assertEqual(self.counter.version, version)
        self.assertEqual(self.counter.bill_count(), original_bills)
        self.assertEqual(self.counter.data()['stock'], original_stock)
        qr_kots = [k for k in self.counter.data()['kots'] if k.get('qr') == 'g_reboot']
        self.assertEqual(len(qr_kots), 1)
        self.assertEqual(qr_kots[0]['items'][0]['qty'], 2)
        self.assertEqual(self.counter.query('inbound-qr', {'status':'accepted'})['count'], 1)
        self.assertEqual(self.counter.sdb.con().execute(
            "PRAGMA quick_check").fetchone()[0], 'ok')


if __name__ == '__main__':
    unittest.main()
