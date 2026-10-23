"""The wcf2xml.py and xml2wcf.py scripts."""

import os
import subprocess
import sys
import unittest

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(script, data, *args, env=None):
    return subprocess.run([sys.executable, os.path.join(TOP, script)] + list(args),
                          input=data, capture_output=True, cwd=TOP,
                          env=dict(os.environ, **(env or {})))


class CliTests(unittest.TestCase):

    def test_round_trip_in_utf8_whatever_the_locale(self):
        for mode in ([], ['--nbfse']):
            with self.subTest(mode=mode):
                binary = run('xml2wcf.py', '<a b="é">€</a>'.encode(), *mode)
                self.assertEqual(0, binary.returncode, binary.stderr)
                xml = run('wcf2xml.py', binary.stdout, *mode,
                          env={'PYTHONIOENCODING': 'ascii'})
                self.assertEqual(0, xml.returncode, xml.stderr)
                self.assertEqual('<a b="é">€</a>'.encode(), xml.stdout)

    def test_invalid_input_is_an_error_message(self):
        for script, data in (('wcf2xml.py', b'\x40\x01'), ('xml2wcf.py', b'<a>')):
            with self.subTest(script=script):
                result = run(script, data)
                self.assertEqual(1, result.returncode)
                self.assertIn(b'error:', result.stderr)
                self.assertNotIn(b'Traceback', result.stderr)

    def test_no_quotas(self):
        deep = b'\x40\x01a' * 100 + b'\x01' * 100
        self.assertEqual(1, run('wcf2xml.py', deep).returncode)
        self.assertEqual(0, run('wcf2xml.py', deep, '--no-quotas').returncode)


if __name__ == '__main__':
    unittest.main()
