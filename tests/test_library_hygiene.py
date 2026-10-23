import subprocess
import sys
import unittest


class LibraryHygieneTest(unittest.TestCase):

    def test_import_does_not_configure_logging(self):
        # A library must leave the logging configuration to the application:
        # logging.basicConfig() at import time would install a root handler
        # and turn the application's own basicConfig() call into a no-op.
        code = ('import logging, wcf.records, wcf.xml2records, wcf.session; '
                'print(len(logging.getLogger().handlers))')
        out = subprocess.check_output([sys.executable, '-c', code])
        self.assertEqual(b'0', out.strip())


if __name__ == '__main__':
    unittest.main()
