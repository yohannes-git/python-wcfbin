#!/usr/bin/env python3
"""Run the whole test suite, as "python -m unittest discover -s tests -t ."
does: python -m tests.alltests"""

import os
import sys
import unittest


def suite():
    top = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return unittest.defaultTestLoader.discover(os.path.join(top, 'tests'),
                                               top_level_dir=top)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=1).run(suite())
    sys.exit(0 if result.wasSuccessful() else 1)
