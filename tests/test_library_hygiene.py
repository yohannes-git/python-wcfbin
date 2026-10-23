import unittest

from tests.support import run_python


class LibraryHygieneTest(unittest.TestCase):

    def test_import_does_not_configure_logging(self):
        # A library must leave the logging configuration to the application:
        # logging.basicConfig() at import time would install a root handler
        # and turn the application's own basicConfig() call into a no-op.
        code = ('import logging, wcf.records, wcf.xml2records, wcf.session; '
                'print(len(logging.getLogger().handlers))')
        self.assertEqual('0', run_python(code).strip())


if __name__ == '__main__':
    unittest.main()
