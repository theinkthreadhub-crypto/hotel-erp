"""Phase 3.5c: isolated legacy-hotel upgrade and safe SQLite backup/restore.

All data is synthetic in temporary directories; never opens live hotel files.
"""
import gzip
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,ROOT)
sys.path.insert(0,os.path.dirname(__file__))
import app_main as A
import setu_sqlite as S
from sqlite_phase2_test import sample_doc
from sqlite_phase2b_test import migrated

def file_hash(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(65536),b''):
            h.update(b)
    return h.hexdigest()

class SafeClientRestore(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(prefix='horeca35c-')
        self.folder=migrated(self.t.name,sample_doc(128))
        self.original_json=os.path.join(self.folder,'setu-db.json')
        self.json_hash=file_hash(self.original_json)
        self.store=A.SqliteSetuStore(self.folder)
        self.hotel=self.store.hotel_id()
        self.guest='g_upgrade_01'
        events=[
            {'id':'evt_1_upgrade','seq':1,'event_type':'qr_order',
             'entity_id':self.guest,'payload':{
               'order_id':self.guest,'table':'T-3',
               'items':[{'mid':'m1','name':'Dish 1 पनीर','qty':2,'price':290}]
             }},
            {'id':'evt_2_upgrade','seq':2,'event_type':'qr_status',
             'entity_id':self.guest,'payload':{
               'order_id':self.guest,'status':'accepted'
             }}
        ]
        def get(url,path,headers):
            from urllib.parse import urlsplit,parse_qs
            since=int(parse_qs(urlsplit(path).query).get('since',['0'])[0])
            return 200,json.dumps({'ok':True,'hotel':self.hotel,
                                   'events':[e for e in events if e['seq']>since]})
        def ack(url,path,payload,headers):
            data=json.loads(payload)
            if path=='/api/qr/applied':
                return 200,json.dumps({'ok':True,'id':data['id'],'kot':data['kot']})
            return 200,json.dumps({'ok':True,'hotel':self.hotel,'acked_ids':data['event_ids']})
        self.receiver=S.InboundSyncReceiver(
            store=self.store,url='https://synthetic.invalid',
            hotel=self.hotel,key='only_for_tests',enabled=True,
            http_get_fn=get,http_post_fn=ack
        )
        applied=self.receiver.fetch_and_apply_once()
        self.assertEqual(applied['status'],'ok',applied)
        self.assertEqual(applied['applied'],2)
        self.assertEqual(self.store.query('inbound-qr',{'status':'accepted'})['count'],1)
        self.before_doc=self.store.sdb.export_document()
        self.before_hash=S.canonical_hash(self.before_doc)
        self.before_bill_count=self.store.bill_count()
        self.before_kots=self.store.sdb.con().execute('SELECT COUNT(*) FROM kots').fetchone()[0]
        self.before_cursor=self.receiver.get_last_applied_seq()
        self.before_version=self.store.version
        self.before_conflicts=self.store.sdb.con().execute(
            'SELECT COUNT(*) FROM sync_conflicts').fetchone()[0]
        self.backup=os.path.join(self.t.name,'setu-upgrade.sqlite.gz')
        result=self.store.sdb.backup_to(self.backup,self.store.version,keep=0)
        self.assertTrue(result['verified'],result)
    def tearDown(self):
        self.store.sdb.close()
        self.t.cleanup()

    def test_restore_to_fresh_folder_preserves_bills_kot_stock_and_cursor(self):
        new_dir=os.path.join(self.t.name,'new-pc')
        os.mkdir(new_dir)
        target=os.path.join(new_dir,S.DB_FILE)
        report=S.restore_backup(self.backup,target,expected_hotel_id=self.hotel)
        self.assertEqual(report['integrity'],'ok')
        self.assertEqual(report['hotel_id'],self.hotel)
        S.write_flag(new_dir,{'engine':'sqlite','note':'synthetic QA restore'})
        restored=A.SqliteSetuStore(new_dir)
        try:
            self.assertEqual(S.canonical_hash(restored.sdb.export_document()),self.before_hash)
            self.assertEqual(restored.bill_count(),self.before_bill_count)
            self.assertEqual(restored.version,self.before_version)
            self.assertEqual(restored.sdb.con().execute(
                'SELECT COUNT(*) FROM kots').fetchone()[0],self.before_kots)
            self.assertEqual(restored.sdb.con().execute(
                'SELECT COUNT(*) FROM sync_conflicts').fetchone()[0],self.before_conflicts)
            self.assertEqual(restored.sdb.con().execute(
                "SELECT seq FROM inbound_cursor_state WHERE name='inbound'").fetchone()[0],
                self.before_cursor)
            state=restored.sdb.con().execute(
                'SELECT status,cloud_applied_at,kot_id FROM inbound_qr_orders WHERE order_id=?',
                (self.guest,)).fetchone()
            self.assertEqual(state[0],'accepted')
            self.assertIsNotNone(state[1])
            self.assertTrue(state[2])
            self.assertEqual(restored.sdb.con().execute(
                'PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(file_hash(self.original_json),self.json_hash)
        finally:
            restored.sdb.close()

    def test_hotel_mismatch_rejected_and_no_target_created(self):
        target=os.path.join(self.t.name,'cross-hotel.sqlite')
        with self.assertRaisesRegex(S.StoreError,'Hotel ID mismatch'):
            S.restore_backup(self.backup,target,expected_hotel_id='ANOTHER_HOTEL')
        self.assertFalse(os.path.exists(target))
        self.assertFalse(os.path.exists(target+'.restore'))

    def test_existing_database_not_overwritten(self):
        target=os.path.join(self.folder,S.DB_FILE)
        original=file_hash(target)
        with self.assertRaisesRegex(S.StoreError,'empty destination'):
            S.restore_backup(self.backup,target,expected_hotel_id=self.hotel)
        self.assertEqual(file_hash(target),original)

    def test_corrupt_archive_fails_closed_and_cleans_temp(self):
        target=os.path.join(self.t.name,'corrupt-destination.sqlite')
        bad=os.path.join(self.t.name,'truncated.sqlite.gz')
        with open(self.backup,'rb') as f:
            data=f.read()
        with open(bad,'wb') as f:
            f.write(data[:max(10,len(data)//4)])
        with self.assertRaises((OSError,EOFError,Exception)):
            S.restore_backup(bad,target,expected_hotel_id=self.hotel)
        self.assertFalse(os.path.exists(target))
        self.assertFalse(os.path.exists(target+'.restore'))

    def test_a_wrong_hotel_existing_target_is_never_modified(self):
        target=os.path.join(self.t.name,'other-hotel.sqlite')
        with open(target,'wb') as f:
            f.write(b'synthetic-existing-unrelated-data')
        before=file_hash(target)
        with self.assertRaises(S.StoreError):
            S.restore_backup(self.backup,target,expected_hotel_id=self.hotel)
        self.assertEqual(file_hash(target),before)

if __name__=='__main__':
    unittest.main()
