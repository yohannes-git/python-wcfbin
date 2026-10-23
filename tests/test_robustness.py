"""Repeatable fuzz-like and malformed-record checks (no external dependency)."""

import io
import random
import unittest
from xml.sax.saxutils import escape
from xml.etree import ElementTree as ET

from wcf.records import Record, dump_records
from wcf.xml2records import XMLParser
from wcf.session import BinaryXmlSession
from wcf.records.text import QNameDictionaryTextRecord


class RobustnessTests(unittest.TestCase):
    def test_rejects_bad_qname_prefix(self):
        # A QNameDictionaryText prefix is the zero-based index for a..z.
        for invalid in (26, 255):
            wire = b'\x40\x01r\xbd' + bytes((invalid,)) + b'\x02'
            with self.subTest(index=invalid), self.assertRaises(ValueError):
                Record.parse(io.BytesIO(wire))
        for value in ('', 'A', '{', 'ab'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                QNameDictionaryTextRecord(value, 2).to_bytes()

    def test_random_xml_conversion_infoset_and_roundtrip(self):
        rng = random.Random(20261023)
        outbound = BinaryXmlSession()
        inbound = BinaryXmlSession()
        for i in range(500):
            name = rng.choice(['myRoot', 'Invoice', 'Body', 'Package', 'Version', 'Node'])
            text = ''.join(rng.choice('ab 0123<&\t\nΩé') for _ in range(rng.randrange(0, 45)))
            attrs = ''.join(rng.choice('9.0 <&\r\t\nΩé') for _ in range(rng.randrange(0, 35)))
            xml = ('<p:%s xmlns:p="urn:test" revision="%s">%s</p:%s>' %
                   (name, escape(attrs, {'"': '&quot;', '\r': '&#xD;',
                                        '\t': '&#x9;', '\n': '&#xA;'}),
                    escape(text), name))
            if i == 0:
                data = outbound.encode_xml(xml, new_strings=['myRoot', 'Invoice', 'Package',
                                                              'Version', 'Node', 'urn:test',
                                                              'revision'])
            else:
                data = outbound.encode_xml(xml)
            decoded = inbound.parse_document(data)
            self.assertEqual(data, decoded.to_bytes(), msg='iteration %d' % i)
            self.assertEqual(ET.tostring(ET.fromstring(xml)),
                             ET.tostring(ET.fromstring(decoded.render_xml())),
                             msg='iteration %d' % i)

    def test_fuzz_random_binary_always_fail_or_byte_preserve(self):
        rng = random.Random(0xABC123)
        for i in range(4000):
            blob = rng.randbytes(rng.randrange(0, 40))
            try:
                records = Record.parse(io.BytesIO(blob))
            except (ValueError, UnicodeError, KeyError, IndexError, TypeError,
                    OverflowError, Exception):
                continue
            self.assertEqual(blob, dump_records(records), msg='iteration %d' % i)

    def test_float_and_decimal_as_lexical_strings(self):
        for literal in ['8.0', '1.0.0', '0.00001', '0001', 'NaN', 'true',
                        'aabbccddeeff', '11e-4']:
            with self.subTest(literal=literal):
                text = '<version>' + literal + '</version>'
                self.assertEqual(text,
                                 BinaryXmlSession().parse_document(
                                     BinaryXmlSession().encode_xml(text)
                                 ).render_xml())


if __name__ == '__main__':
    unittest.main()
