"""The doctests of the library modules."""

import doctest

import wcf.records
from wcf import datatypes, dictionary, session, xml2records, xmltext
from wcf.records import attributes, base, elements, text


def load_tests(loader, tests, ignore):
    for module in (datatypes, dictionary, session, xml2records, xmltext,
                   wcf.records, base, text, attributes, elements):
        tests.addTests(doctest.DocTestSuite(module))
    return tests
