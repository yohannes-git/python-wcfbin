"""XML to records: every invalid input is a ValueError, raised early."""

import io
import time
import unittest

from wcf.datatypes import Decimal
from wcf.records import (Record, dump_records, render_xml, Chars32TextRecord,
                         Bytes32TextRecord)
from wcf.session import BinaryXmlSession
from wcf.xml2records import XMLParser


class XmlInputTests(unittest.TestCase):

    def test_malformed_xml(self):
        for xml in ('<unclosed>', '<a></b>', '<a b="1" b="2"/>', 'text',
                    '<a>&undefined;</a>', '<a>\x01</a>'):
            with self.subTest(xml=xml):
                with self.assertRaises(ValueError):
                    XMLParser.parse(xml)
                with self.assertRaises(ValueError):
                    BinaryXmlSession().encode_xml(xml)

    def test_names_must_be_ncnames(self):
        # a non namespace-aware parser takes "b:c" as the local name
        for xml in ('<a:b:c xmlns:a="urn:a"/>',
                    '<r xmlns:a="urn:a" a:b:c="1"/>'):
            with self.subTest(xml=xml), self.assertRaises(ValueError):
                XMLParser.parse(xml)

    def test_decimal_type(self):
        types = {'/d': 'decimal'}
        for text, scale, rendered in (('1.50', 2, '1.5'), ('-.5', 1, '-0.5'),
                                      ('79228162514264337593543950335', 0,
                                       '79228162514264337593543950335')):
            with self.subTest(text=text):
                records = XMLParser.parse('<d>%s</d>' % text, type_overrides=types)
                self.assertEqual(scale, records[0].childs[0].value.scale)
                self.assertEqual('<d>%s</d>' % rendered, render_xml(
                    Record.parse(io.BytesIO(dump_records(records)))))
        start = time.monotonic()
        for text in ('abc', '1E+5000000', '1e2', ' ', '.', '1.2.3',
                     '79228162514264337593543950336', '0.' + '1' * 29,
                     '9' * 100000):
            with self.subTest(text=text[:20]), self.assertRaises(ValueError):
                XMLParser.parse('<d>%s</d>' % text, type_overrides=types)
        self.assertLess(time.monotonic() - start, 1)
        for args in ((False, 1 << 32, 0, 0), (False, 0, 1 << 64, 0),
                     (False, -1, 0, 0), (False, 0, 0, 29)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                Decimal(*args)

    def test_float_out_of_range(self):
        records = XMLParser.parse('<f>1e39</f>', type_overrides={'/f': 'float'})
        with self.assertRaises(ValueError):
            dump_records(records)

    def test_length_prefixed_bounds(self):
        # Chars32Text and Bytes32Text have a signed INT32 length
        self.assertEqual(0x7fffffff, Chars32TextRecord.max_length())
        self.assertEqual(0x7fffffff, Bytes32TextRecord.max_length())


if __name__ == '__main__':
    unittest.main()
