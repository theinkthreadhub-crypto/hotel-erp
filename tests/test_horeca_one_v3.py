"""HoReCa One reference-accurate V3 UI smoke tests. Non-destructive."""
import re
import json
import shutil
import tempfile
import subprocess
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HTML=(ROOT/"hotel_erp.html").read_text(encoding="utf-8")
HOOK=(ROOT/"installer"/"horeca_v3_preview_hook.py").read_text(encoding="utf-8")
SCREENS=("gateway","bill","bills","sessions","online","qr","captain","kitchen",
         "tokens","reservations","purchase","stock","suppliers","expense","cash",
         "daybook","gst","analytics","wa-reports","settings","guide","ai")

class HoReCaV3Tests(unittest.TestCase):
    def test_approved_palette_and_layout(self):
        for item in ("HoReCa One V3 Reference Skin","--primary:#1461df",
                     "ho-v3-dashboard","ho-v3-dashboard-primary",
                     "ho-v3-kpi-grid","ho-v3-add-chip","ho-v3-shift-metrics",
                     "ho-v3-settings-layout","horeca-pos-workspace"):
            self.assertIn(item,HTML)
    def test_real_functions_preserved(self):
        for fn in ("scrBill","scrGateway","scrSettings","scrSessions","scrPurchase",
                   "scrBills","scrReports","scrGst","finalizePakkaBill","saveKacchaBill",
                   "savePurchase","save","applyTheme","go"):
            self.assertIn("function "+fn+"(",HTML)
    def test_routes_preserved(self):
        block=HTML.split("const SCREENS = {",1)[1].split("};",1)[0]
        for route in SCREENS:
            self.assertIn(route+":",block) if "-" not in route else self.assertIn("'"+route+"':",block)
    def test_correct_preference_isolation(self):
        self.assertIn("html[data-theme^=\"horeca_\"]",HTML)
        self.assertIn("resetThemeDefault()",HTML)
        self.assertIn("hoV3SettingsLayout();",HTML)
        self.assertIn("posCards() === 'off' ? 'standard' : posCards()",HTML)
    def test_preview_is_isolated(self):
        self.assertIn("HoReCaOneReferenceV3",HOOK)
        self.assertIn("8163",HOOK)
        self.assertIn("127.0.0.1:9876",HOOK)
        self.assertIn("if not os.path.exists(db)",HOOK)
        self.assertIn("SEC.hash_secret(demo_pw)",HOOK)
    @unittest.skipUnless(shutil.which("node"),"node missing")
    def test_embedded_js_parse(self):
        scripts=re.findall(r'<script(?:\s[^>]*)?>([\s\S]*?)</script>',HTML)
        self.assertGreater(len(scripts),0)
        with tempfile.TemporaryDirectory() as temp:
            for i,script in enumerate(scripts):
                path=Path(temp)/("inline_%s.js"%i)
                path.write_text(script,encoding="utf-8")
                r=subprocess.run(["node","--check",str(path)],text=True,capture_output=True)
                self.assertEqual(r.returncode,0,r.stderr[:900])

if __name__=="__main__":
    unittest.main()
