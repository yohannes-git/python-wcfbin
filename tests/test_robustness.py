"""Repeatable fuzz-like and malformed-record checks (no external dependency)."""

import io
import random
import unittest
from xml.sax.saxutils import escape
from xml.etree import ElementTree as ET

from wcf.records import Record, dump_records, render_xml
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
            except ValueError:
                # every malformed input must be reported as ValueError
                continue
            self.assertEqual(blob, dump_records(records), msg='iteration %d' % i)

    @staticmethod
    def all_text_document():
        """A document with one record of every text type, as attribute
        values and as content, a list and an array."""
        from wcf.datatypes import Decimal
        from wcf.records import (
            ShortElementRecord, ShortAttributeRecord, ArrayRecord,
            ZeroTextRecord, OneTextRecord, FalseTextRecord, TrueTextRecord,
            Int8TextRecord, Int16TextRecord, Int32TextRecord, Int64TextRecord,
            UInt64TextRecord, FloatTextRecord, DoubleTextRecord,
            DecimalTextRecord, DatetimeTextRecord, Chars8TextRecord,
            Chars16TextRecord, Chars32TextRecord, Bytes8TextRecord,
            Bytes16TextRecord, Bytes32TextRecord, StartListTextRecord,
            EmptyTextRecord, DictionaryTextRecord, UniqueIdTextRecord,
            UuidTextRecord, TimeSpanTextRecord, BoolTextRecord,
            UnicodeChars8TextRecord, UnicodeChars16TextRecord,
            UnicodeChars32TextRecord, QNameDictionaryTextRecord)
        uuid = '33221100-5544-7766-8899-aabbccddeeff'
        texts = [
            ZeroTextRecord(), OneTextRecord(), FalseTextRecord(),
            TrueTextRecord(), Int8TextRecord(-1), Int16TextRecord(-32768),
            Int32TextRecord(2147483647), Int64TextRecord(1 << 40),
            UInt64TextRecord((1 << 64) - 1), FloatTextRecord(1.5),
            DoubleTextRecord(2.5), DecimalTextRecord(Decimal(False, 0, 5123456, 6)),
            DatetimeTextRecord(632834208000000000, 1), Chars8TextRecord('abc'),
            Chars16TextRecord('abc'), Chars32TextRecord('abc'),
            Bytes8TextRecord(b'\x01\x02'), Bytes16TextRecord(b'\x01\x02'),
            Bytes32TextRecord(b'\x01\x02'),
            StartListTextRecord([Int8TextRecord(1), TrueTextRecord()]),
            EmptyTextRecord(), DictionaryTextRecord(2), UniqueIdTextRecord(uuid),
            UuidTextRecord(uuid), TimeSpanTextRecord(-3440000000),
            BoolTextRecord(True), UnicodeChars8TextRecord('ab'),
            UnicodeChars16TextRecord('ab'), UnicodeChars32TextRecord('ab'),
            QNameDictionaryTextRecord('b', 2)]
        root = ShortElementRecord('r')
        for i, text in enumerate(texts):
            root.attributes.append(ShortAttributeRecord('a%d' % i, text))
        content = ShortElementRecord('c')
        content.childs.extend(texts)
        root.childs.append(content)
        root.childs.append(ArrayRecord(ShortElementRecord('i'),
                                       [Int32TextRecord(1), Int32TextRecord(2)], []))
        return dump_records([root])

    def test_truncated_input_raises_value_error(self):
        data = self.all_text_document()
        self.assertEqual(data, dump_records(Record.parse(io.BytesIO(data))))
        for cut in range(1, len(data)):
            with self.subTest(cut=cut), self.assertRaises(ValueError):
                Record.parse(io.BytesIO(data[:cut]))

    def test_mutated_input_raises_only_value_error(self):
        data = self.all_text_document()
        rng = random.Random(0x5EED)
        for i in range(3000):
            blob = bytearray(data)
            for _ in range(rng.randrange(1, 4)):
                blob[rng.randrange(len(blob))] = rng.randrange(256)
            try:
                records = Record.parse(io.BytesIO(bytes(blob)))
                render_xml(records)
            except ValueError:
                continue

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
