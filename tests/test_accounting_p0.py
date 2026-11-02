import subprocess
import unittest
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

class TestAccountingP0(unittest.TestCase):
    """
    Automated accounting verification tests based on Part I & Part B of the
    HoReCa One Complete Accounting & Financial Reporting Development Blueprint.
    """

    @classmethod
    def setUpClass(cls):
        cls.test_script_path = os.path.join(os.path.dirname(__file__), 'run_accounting_p0_suite.cjs')

    def run_node_suite(self):
        result = subprocess.run(
            ['node', self.test_script_path],
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        return result

    def test_accounting_suite_execution(self):
        res = self.run_node_suite()
        print(res.stdout)
        if res.stderr:
            print("STDERR:", res.stderr)
        self.assertEqual(res.returncode, 0, f"Accounting P0 suite failed with returncode {res.returncode}")

if __name__ == '__main__':
    unittest.main()
