"""Read-only smoke checks for the HoReCa One premium UI integration.

Run from the repository root:
    python -m unittest discover -s tests -p "test_horeca_one_ui.py" -v

No hotel is registered, no DB is changed and no cloud API is called.
"""
from pathlib import Path
import json
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "hotel_erp.html"
TEXT = HTML.read_text(encoding="utf-8")

EXPECTED_SCREENS = [
    "gateway", "bill", "bills", "sessions", "online", "qr", "captain",
    "kitchen", "tokens", "reservations", "purchase", "stock",
    "suppliers", "expense", "cash", "daybook", "gst", "analytics",
    "wa-reports", "settings", "support", "ai",
]

class HoReCaOneStaticChecks(unittest.TestCase):
    def test_brand(self):
        self.assertIn("HoReCa One", TEXT)
        self.assertIn("Powered by Setu Pro", TEXT)
        self.assertIn('class="horeca-side-brand"', TEXT)

    def test_premium_theme_only(self):
        self.assertIn('html[data-theme="horeca_light"]{', TEXT)
        self.assertIn('html[data-theme="horeca_dark"]{', TEXT)
        self.assertIn('html[data-theme^="horeca_"]', TEXT)
        self.assertIn("END HORECA ONE PREMIUM UI", TEXT)
        self.assertIn("Original Classic", TEXT)

    def test_new_customer_default(self):
        seed = TEXT.split("function seed(){", 1)[1].split("function ", 1)[0]
        self.assertIn("theme: 'horeca_light'", seed)
        self.assertIn("dashStyle: 'modern'", seed)
        self.assertIn("...s.settings", TEXT)  # Existing accounts retain saved config.

    def test_three_sidebar_modes(self):
        for mode in ("expanded", "compact", "hidden"):
            self.assertIn("'"+mode+"'", TEXT)
        for function in ("setHoReCaSidebarMode", "getHoReCaSidebarMode",
                         "toggleHoReCaSidebar", "initHoReCaSidebar"):
            self.assertIn("function "+function+"(", TEXT)
        self.assertIn("horeca_sidebar_mode", TEXT)
        self.assertIn("document.body.dataset.horecaScreen = s;", TEXT)

    def test_22_real_screen_routes(self):
        map_block = TEXT.split("const SCREENS = {", 1)[1].split("};", 1)[0]
        for screen in EXPECTED_SCREENS:
            self.assertRegex(map_block, r"(?m)^\s*['\"]?" + re.escape(screen) +
                             r"['\"]?\s*:")

    def test_in_app_learning_center(self):
        self.assertIn("guide: scrHoGuide", TEXT)
        self.assertIn("'User Guide & Training','guide','Utilities'", TEXT)
        self.assertIn("function hoFilterGuide(", TEXT)
        self.assertIn("function hoBeginLesson(", TEXT)
        self.assertIn("function hoGuideAnswer(", TEXT)
        self.assertIn("const HO_HELP = {", TEXT)
        articles = TEXT.split("const HO_HELP = {", 1)[1].split("};", 1)[0]
        for screen in EXPECTED_SCREENS:
            self.assertTrue(
                any(line.lstrip().startswith(screen + ":[") or
                    line.lstrip().startswith('"' + screen + '":[')
                    for line in articles.splitlines()),
                "Missing guide for: " + screen,
            )
        self.assertIn("m[2] === 'guide'", TEXT)
        self.assertIn("s !== 'guide'", TEXT)

    def test_guided_training_is_read_only(self):
        block = TEXT.split("function hoRenderLesson()", 1)[1].split(
            "function hoGuideAnswer(", 1)[0]
        self.assertIn("STEP", block)
        self.assertNotIn("finalizePakkaBill(", block)
        self.assertNotIn("save()", block)
        self.assertNotIn("srvPush(", block)

    def test_ai_guidance_is_local_first(self):
        self.assertIn("const verifiedHelp = hoGuideAnswer(q);", TEXT)
        self.assertIn("if(verifiedHelp)", TEXT)

    def test_core_logic_still_present(self):
        for function in ("scrBill", "scrBills", "scrKitchen", "scrStock",
                         "scrWaReports", "scrGst", "scrReports", "applyTheme",
                         "save", "go"):
            self.assertIn("function "+function+"(", TEXT)

    def test_pwa_brand_and_cache(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("HoReCa One", manifest["name"])
        self.assertIn("HoReCa One", manifest["short_name"])
        sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        self.assertTrue("setu-pos-v69" in sw or "setu-pos-v70" in sw, "Cache name must follow versioning")
        self.assertIn("hotel_erp.html", sw)

    @unittest.skipUnless(shutil.which("node"), "Node.js unavailable")
    def test_embedded_scripts_parse_with_node(self):
        scripts = re.findall(r"<script(?:\s[^>]*)?>([\s\S]*?)</script>", TEXT)
        self.assertGreater(len(scripts), 0)
        with tempfile.TemporaryDirectory() as temp:
            for i, js in enumerate(scripts):
                path = Path(temp) / ("inline_%d.js" % i)
                path.write_text(js, encoding="utf-8")
                result = subprocess.run(["node", "--check", str(path)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0,
                                 "Script %s: %s" % (i, result.stderr[:1000]))

if __name__ == "__main__":
    unittest.main()
