"""Regression guard (TD-0011, SEC-001): no live credential or credential default is committed.

Scans every file tracked by Git (text only) for well-known provider key formats and private keys, and every Python
file for os.environ.get / os.getenv calls that give a secret-looking variable a non-empty literal default.
Matches are reported as file:line plus the rule name only; the matched text is never printed.
"""
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATTERNS = {
    'Resend API key': re.compile(r're_[A-Za-z0-9]{8,}_[A-Za-z0-9]{12,}'),
    'AWS access key id': re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    'Google API key': re.compile(r'\bAIza[0-9A-Za-z_\-]{35}\b'),
    'GitHub token': re.compile(r'\bgh[pousr]_[A-Za-z0-9]{36,}\b'),
    'Slack token': re.compile(r'\bxox[abprs]-[A-Za-z0-9-]{10,}'),
    'Stripe live key': re.compile(r'\b[sr]k_live_[A-Za-z0-9]{16,}'),
    'OpenAI / Anthropic key': re.compile(r'\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{32,}'),
}
# A private key is the header FOLLOWED by key material (a bare header is only a placeholder / help text)
PRIVATE_KEY = re.compile(r'-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----\s*(?:\\n)?\s*[A-Za-z0-9+/=]{40,}')
SECRET_DEFAULT = re.compile(
    r"""(?:os\.environ\.get|os\.getenv)\(\s*['"]([A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|PASS)[A-Z0-9_]*)['"]\s*,\s*['"]([^'"]+)['"]""")
SKIP_DIRS = ('node_modules/',)
SKIP_EXT = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.ico', '.zip', '.exe', '.apk', '.pdf', '.woff', '.woff2', '.ttf', '.jar', '.keystore')


def tracked_files():
    out = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True).stdout
    return [f for f in out.decode('utf-8', 'replace').split('\0') if f and not f.startswith(SKIP_DIRS) and not f.lower().endswith(SKIP_EXT)]


def scan(paths=None):
    hits = []
    for rel in paths if paths is not None else tracked_files():
        try:
            with open(os.path.join(ROOT, rel), 'rb') as fh:
                raw = fh.read(8 * 1024 * 1024)
        except OSError:
            continue
        if b'\0' in raw[:4096]:
            continue
        text = raw.decode('utf-8', 'replace')
        for m in PRIVATE_KEY.finditer(text):
            hits.append(f"{rel}:{text.count(chr(10), 0, m.start()) + 1}: Private key block")
        for no, line in enumerate(text.splitlines(), 1):
            for name, rx in PATTERNS.items():
                if rx.search(line):
                    hits.append(f'{rel}:{no}: {name}')
            if rel.endswith('.py'):
                for m in SECRET_DEFAULT.finditer(line):
                    hits.append(f'{rel}:{no}: non-empty default for secret variable {m.group(1)}')
    return hits


class SecretScan(unittest.TestCase):
    def test_no_committed_credentials(self):
        hits = scan()
        self.assertEqual(hits, [], 'Remove these credentials from the repository and rotate them:\n' + '\n'.join(hits))

    def test_scanner_detects_a_planted_default(self):
        """The guard itself works: a planted fake default is reported (fake value, built at run time)."""
        import tempfile
        fake = 're_' + 'A' * 10 + '_' + 'B' * 16
        with tempfile.NamedTemporaryFile('w', suffix='.py', dir=ROOT, delete=False) as fh:
            fh.write('K = os.environ' + ".get('MAIL_API_KEY', '" + fake + "')\n")
            name = os.path.basename(fh.name)
        try:
            hits = scan([name])
        finally:
            os.unlink(os.path.join(ROOT, name))
        self.assertTrue(any('Resend API key' in h for h in hits), hits)
        self.assertTrue(any('MAIL_API_KEY' in h for h in hits), hits)
        self.assertFalse(any(fake in h for h in hits), 'the scanner must never print the secret')


if __name__ == '__main__':
    unittest.main(verbosity=1)
