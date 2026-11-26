"""Every picture the screen asks for (logo on the lock screen, login, top bar, Super Admin cards) is served by the counter
program and packed into the Windows program, so nothing shows as a broken image in the installer (BUG-0035).

    python tests/counter_static_assets_test.py
"""
import glob
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')


def local_images():
    html = open(os.path.join(ROOT, 'hotel_erp.html'), encoding='utf-8').read()
    names = set(re.findall(r'src="([A-Za-z0-9_.\-]+\.(?:png|jpg|ico|svg))"', html))
    names |= set(re.findall(r"'\./([A-Za-z0-9_.\-]+\.(?:png|jpg|ico|svg))'", open(os.path.join(ROOT, 'sw.js'), encoding='utf-8').read()))
    return sorted(names)


class StaticAssets(unittest.TestCase):
    def test_01_every_local_image_is_served_by_the_counter(self):
        s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
        d = tempfile.mkdtemp(prefix='horeca-assets-')
        p = subprocess.Popen([sys.executable, 'app_main.py', '--server', '--port', str(port), '--data', d], cwd=ROOT,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={**os.environ, 'SETU_BACKUP': 'off', 'SETU_CLOUD_URL': 'http://127.0.0.1:9'})
        self.addCleanup(lambda: (p.kill(), p.wait(10)))
        for _ in range(150):
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{port}/api/ping', timeout=1).read()
                break
            except OSError:
                time.sleep(0.2)
        names = local_images()
        self.assertIn('horeca-icon-dark.png', names)
        for n in names:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/{n}', timeout=10) as r:
                body = r.read()
                self.assertEqual(r.status, 200, n)
                self.assertEqual(len(body), os.path.getsize(os.path.join(ROOT, n)), n)

    def test_02_every_local_image_is_packed_into_the_windows_program(self):
        for f in ['.github/workflows/build-exe.yml', 'Build-New-EXE.bat', 'Aghanya-Devanya-Hotel-ERP.spec']:
            text = open(os.path.join(ROOT, f), encoding='utf-8').read()
            for n in local_images():
                self.assertTrue(f'"{n};."' in text or f"('{n}', '.')" in text, f'{n} is not packed in {f}')

    def test_03_every_local_image_is_on_the_cloud(self):
        text = open(os.path.join(ROOT, 'cloud', 'scripts', 'copy-assets.mjs'), encoding='utf-8').read()
        for n in local_images():
            self.assertIn(f"'{n}'", text, f'{n} is not copied to the cloud')


if __name__ == '__main__':
    unittest.main(verbosity=2)
