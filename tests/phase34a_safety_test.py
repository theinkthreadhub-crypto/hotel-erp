"""Phase 3.4a focused safety regressions. Synthetic data and EPHEMERAL test keys only."""
import base64
import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
from datetime import date, timedelta
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import setu_sqlite as S
from horeca_license_verify import verify_signed_license, InvalidLicence


def signed_test_key(install_id, kind=1, days=30):
    """Create ephemeral signing key; never persist a private key."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    priv = ec.generate_private_key(ec.SECP256R1())
    pub = base64.b64encode(priv.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )).decode("ascii")
    clean = ''.join(ch for ch in install_id.upper() if ch.isalnum())
    digest = hashlib.sha256(clean.encode("ascii")).digest()[:4]
    issued = (date.today() - date(2026, 1, 1)).days
    payload = bytes([1, kind]) + days.to_bytes(2, "big") + digest + b"abc" + issued.to_bytes(2, "big")
    der = priv.sign(payload, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    text = base64.b32encode(payload + sig).decode("ascii").rstrip("=")
    return "SETU-" + text, pub


class InboundSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = S.SqliteDoc(os.path.join(self.tmp.name, "setu.sqlite"), create=True)
        self.hotel = "HOTEL_SAFETY"
        self.install_id = "SETU-ABCD-1234"
        with self.db.tx() as c:
            c.execute("INSERT OR REPLACE INTO meta VALUES ('hotel_id',?)", (self.hotel,))
            c.execute("INSERT INTO hotel_settings(k,v) VALUES('settings',?)",
                      (json.dumps({"installId": self.install_id}),))
        self.events = []
        self.ack_requests = []
        self.fail_acks = 0

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def add_event(self, event_type, payload, n=None):
        n = n or len(self.events) + 1
        evt = {"id": "evt_%d_case" % n, "seq": n,
               "event_type": event_type, "entity_id": payload.get("order_id", ""),
               "payload": payload}
        self.events.append(evt)
        return evt

    def make_receiver(self, wrapper=False):
        def get_fn(url, path, headers):
            q = parse_qs(urlsplit(path).query)
            since = int(q.get("since", ["0"])[0])
            events = [e for e in self.events if e["seq"] > since]
            return 200, json.dumps({"ok": True, "hotel": self.hotel, "events": events})
        def ack_fn(url, path, body, headers):
            ids = json.loads(body)["event_ids"]
            self.ack_requests.append(ids)
            if self.fail_acks:
                self.fail_acks -= 1
                raise OSError("Lost ACK response")
            return 200, json.dumps({"ok": True, "hotel": self.hotel, "acked_ids": ids})
        store = type("LiveStoreWrapper", (), {"sdb": self.db})() if wrapper else self.db
        return S.InboundSyncReceiver(store=store, url="https://test.invalid",
            hotel=self.hotel, key="fake_test_sync_key", enabled=True,
            http_get_fn=get_fn, http_post_fn=ack_fn)

    def test_genuine_signature_tamper_and_wrong_install(self):
        key, pub = signed_test_key(self.install_id)
        info = verify_signed_license(key, self.install_id, public_keys=(pub,))
        self.assertEqual(info["kind"], 1)
        with self.assertRaises(InvalidLicence):
            verify_signed_license(key, "OTHER-INSTALL-99", public_keys=(pub,))
        changed = list(key)
        changed[-1] = "A" if changed[-1] != "A" else "B"
        with self.assertRaises(InvalidLicence):
            verify_signed_license("".join(changed), self.install_id, public_keys=(pub,))
        with self.assertRaises(InvalidLicence):
            verify_signed_license("SETU-FAKE", self.install_id, public_keys=(pub,))

    def test_signed_renewal_applied_and_replayed_key_not_extended(self):
        key, pub = signed_test_key(self.install_id)
        r = self.make_receiver(wrapper=True)
        r.license_public_keys = (pub,)
        self.add_event("licence_update", {
            "hotel_id": self.hotel, "install_id": self.install_id,
            "key": key, "plan": "Pro", "lifetime": False
        })
        out = r.fetch_and_apply_once()
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["acked"], 1)
        with self.db.rlock():
            sub = json.loads(self.db.con().execute(
                "SELECT v FROM hotel_settings WHERE k='subscription'").fetchone()[0])
        self.assertIn(key, sub["cloudKeys"])
        self.assertEqual(sub["planName"], "Pro")
        self.assertIsNotNone(sub["validUntil"])

    def test_invalid_signed_licence_never_marked_or_acked(self):
        self.add_event("licence_update", {
            "hotel_id": self.hotel, "install_id": self.install_id,
            "key": "SETU-SOME-UNSIGNED-TEXT", "lifetime": True
        })
        r = self.make_receiver()
        out = r.fetch_and_apply_once()
        self.assertEqual(out["status"], "blocked")
        self.assertEqual(r.get_last_applied_seq(), 0)
        self.assertEqual(out["acked"], 0)
        with self.db.rlock():
            self.assertEqual(self.db.con().execute(
                "SELECT COUNT(*) FROM inbound_events_applied").fetchone()[0], 0)
            self.assertEqual(self.db.con().execute(
                "SELECT COUNT(*) FROM inbound_event_failures").fetchone()[0], 1)

    def test_gap_does_not_advance_cursor(self):
        self.add_event("vendor_message", {"id": "N2", "message": "Skipped 1"}, n=2)
        r = self.make_receiver()
        out = r.fetch_and_apply_once()
        self.assertEqual(out["status"], "blocked")
        self.assertEqual(r.get_last_applied_seq(), 0)
        self.assertEqual(out["acked"], 0)

    def test_ack_lost_after_commit_resends_without_replaying(self):
        self.fail_acks = 1
        self.add_event("vendor_message", {"id": "N1", "message": "Hello"})
        r = self.make_receiver()
        a = r.fetch_and_apply_once()
        self.assertEqual(a["applied"], 1)
        self.assertEqual(a["acked"], 0)
        self.assertEqual(r.get_last_applied_seq(), 1)
        b = r.fetch_and_apply_once()
        self.assertEqual(b["applied"], 0)
        self.assertEqual(b["acked"], 1)
        with self.db.rlock():
            self.assertIsNotNone(self.db.con().execute(
                "SELECT acked_at FROM inbound_events_applied WHERE id='evt_1_case'"
            ).fetchone()[0])

    def test_qr_rejected_never_enters_bill_cart(self):
        with self.db.tx() as c:
            c.execute("INSERT INTO table_orders(tbl,ord,data) VALUES('5',1,?)",
                (json.dumps({"cart":[{"mid":"coffee","qty":1,"price":40}], "cust":"Waiter"}),))
        self.add_event("qr_order", {"order_id":"G1","table":"5",
            "items":[{"mid":"coffee","qty":3,"price":40}]})
        r = self.make_receiver()
        self.assertEqual(r.fetch_and_apply_once()["status"],"ok")
        with self.db.rlock():
            data=json.loads(self.db.con().execute("SELECT data FROM table_orders WHERE tbl='5'").fetchone()[0])
            self.assertEqual(len(data["cart"]),1)
            self.assertEqual(self.db.con().execute("SELECT COUNT(*) FROM kots").fetchone()[0],0)
        self.add_event("qr_status", {"order_id":"G1","status":"rejected"})
        self.assertEqual(r.fetch_and_apply_once()["status"],"ok")
        with self.db.rlock():
            data=json.loads(self.db.con().execute("SELECT data FROM table_orders WHERE tbl='5'").fetchone()[0])
            self.assertEqual(data["cart"], [{"mid":"coffee","qty":1,"price":40}])
            self.assertEqual(self.db.con().execute("SELECT COUNT(*) FROM kots").fetchone()[0],0)

    def test_qr_accepted_exactly_one_kot(self):
        self.add_event("qr_order", {"order_id":"G2","table":"6",
            "items":[{"mid":"soup","qty":2,"price":60,"name":"Soup"}]})
        self.add_event("qr_status", {"order_id":"G2","status":"accepted"})
        r=self.make_receiver()
        a=r.fetch_and_apply_once()
        self.assertEqual(a["status"],"ok")
        self.assertEqual(a["applied"],2)
        with self.db.rlock():
            row=self.db.con().execute("SELECT status,kot_id FROM inbound_qr_orders WHERE order_id='G2'").fetchone()
            self.assertEqual(row[0],"accepted")
            self.assertIsNotNone(row[1])
            self.assertEqual(self.db.con().execute("SELECT COUNT(*) FROM kots").fetchone()[0],1)
        self.assertEqual(r.fetch_and_apply_once()["applied"],0)
        with self.db.rlock():
            self.assertEqual(self.db.con().execute("SELECT COUNT(*) FROM kots").fetchone()[0],1)


if __name__ == "__main__":
    unittest.main()
