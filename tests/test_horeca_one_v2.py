"""Read-only checks for premium screen-level UI; no financial records written."""
import unittest
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'hotel_erp.html').read_text(encoding='utf-8')
SW = (ROOT / 'sw.js').read_text(encoding='utf-8')
class HoReCaV2UI(unittest.TestCase):
    def test_screen_markup(self):
        for token in ('horeca-pos-workspace', 'horeca-pos-catalog',
                      'horeca-pos-checkout', 'horeca-pos-total',
                      'horeca-shift-title', 'horeca-shift-hero',
                      'horeca-settings-jump', 'horeca-property-card'):
            self.assertIn(token, HTML)
    def test_premium_theme_opt_in(self):
        self.assertIn("Activate HoReCa One", HTML)
        self.assertIn("setTheme('horeca_light','modern')", HTML)
        self.assertIn('html[data-theme^="horeca_"]', HTML)
        self.assertIn("END HoReCa One Screen-Level Redesign V2", HTML)
    def test_data_logic_preserved(self):
        for name in ('scrBill', 'drawItems', 'drawCart','drawPts','scrSessions',
                     'scrSettings', 'scrGateway','saveKacchaBill',
                     'finalizePakkaBill','applyTheme','go'):
            self.assertIn('function ' + name + '(', HTML)
    def test_cache_changed(self):
        self.assertIn("setu-pos-v70", SW)
    @unittest.skipUnless(shutil.which('node'), 'node unavailable')
    def test_embedded_scripts_parse(self):
        scripts=re.findall(r'<script(?:\\s[^>]*)?>([\\s\\S]*?)</script>', HTML)
        if not scripts:
            # Standard regex used below for script tags with literal whitespace.
            scripts=re.findall(r'<script(?:\s[^>]*)?>([\s\S]*?)</script>', HTML)
        self.assertGreaterEqual(len(scripts),2)
        with tempfile.TemporaryDirectory() as temp:
            for i,src in enumerate(scripts):
                file=Path(temp) / ('app_%d.js'%i)
                file.write_text(src,encoding='utf-8')
                ret=subprocess.run(['node','--check',str(file)],
                                   capture_output=True,text=True)
                self.assertEqual(ret.returncode,0,ret.stderr[:800])
if __name__=='__main__':
    unittest.main()
