import unittest
import os
import sys
import json

# Add hotel-erp to sys.path
sys.path.insert(0, os.path.abspath('hotel-erp'))
import setu_security as SEC

class TestSimplifiedLoginAndAuth(unittest.TestCase):
    def test_password_hashing_and_verification(self):
        pw = "HotelPass@2026"
        h = SEC.hash_secret(pw)
        self.assertTrue(h.startswith("pbkdf2_sha256$") or h.startswith("s1$"), "Should use salted scrypt/pbkdf2 hash")
        self.assertTrue(SEC.verify_secret(pw, h), "Original password must verify")
        self.assertFalse(SEC.verify_secret("WrongPass", h), "Wrong password must be rejected")

    def test_check_pin_with_owner_password(self):
        d = {
            "secure": {
                "owner": SEC.hash_secret("OwnerMaster123")
            },
            "auth": {
                "ownerName": "Rajesh Sharma",
                "hotelId": "HOTEL4820",
                "status": "active"
            },
            "settings": {
                "hotelId": "HOTEL4820",
                "name": "Taj Heritage"
            }
        }
        res = SEC.check_pin(d, "OwnerMaster123")
        self.assertIsNotNone(res)
        self.assertEqual(res[0], "admin")
        self.assertEqual(res[1], "Rajesh Sharma")

        # Wrong password
        self.assertIsNone(SEC.check_pin(d, "WrongPass"))

    def test_login_screen_html_elements(self):
        with open('hotel-erp/hotel_erp.html', 'r', encoding='utf-8') as f:
            html = f.read()

        # Check options
        self.assertIn('Existing Hotel Login', html)
        self.assertIn('+ New Hotel Setup', html)
        self.assertIn('id="exist_hotel_id"', html)
        self.assertIn('id="exist_username"', html)
        self.assertIn('id="exist_password"', html)
        self.assertIn('id="exist_remember"', html)
        self.assertIn('handleUnifiedLogin', html)

        # Check New Hotel Registration fields
        self.assertIn('id="new_hotel_name"', html)
        self.assertIn('id="new_owner_name"', html)
        self.assertIn('id="new_owner_mobile"', html)
        self.assertIn('id="new_admin_username"', html)
        self.assertIn('id="new_admin_password"', html)
        self.assertIn('id="new_confirm_password"', html)
        self.assertIn('handleNewHotelRegister', html)

        # Check Activation step
        self.assertIn('id="disp_new_hotel_id"', html)
        self.assertIn('id="new_activation_key"', html)
        self.assertIn('handleNewHotelActivate', html)
        self.assertIn('copyNewHotelId', html)

    def test_cloud_worker_endpoints(self):
        with open('hotel-erp/cloud/src/worker.js', 'r', encoding='utf-8') as f:
            js = f.read()

        self.assertIn('/api/hotel/register', js)
        self.assertIn('/api/hotel/activate', js)
        self.assertIn('/api/hotel/login', js)
        self.assertIn('hotelRegister', js)
        self.assertIn('hotelActivate', js)
        self.assertIn('hotelLogin', js)
        self.assertIn('/internal/activate', js)
        self.assertIn('/internal/auth', js)

    def test_super_admin_pending_state(self):
        with open('hotel-erp/cloud/static/admin.html', 'r', encoding='utf-8') as f:
            admin_html = f.read()

        self.assertIn("['Pending Activation', 'warn']", admin_html)
        self.assertIn("pending: ['Pending Activation'", admin_html)

if __name__ == '__main__':
    unittest.main()
