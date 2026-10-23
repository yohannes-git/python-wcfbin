"""Additional normative MC-NBFX regression and boundary cases.

These tests intentionally do not depend on the historic implementation tests:
MC-NBFX 2.2.1-2.2.3; MC-NBFSE dictionary resolution is covered as well.
"""
import io
import math
import random
import struct
import unittest

from wcf.dictionary import dictionary_context
from wcf.records import Record, dump_records, render_xml
from wcf.records.attributes import (
    AttributeRecord, DictionaryAttributeRecord, DictionaryXmlnsAttributeRecord,
    PrefixAttributeARecord, PrefixDictionaryAttributeARecord, ShortAttributeRecord,
    ShortDictionaryAttributeRecord, XmlnsAttributeRecord,
)
from wcf.records.elements import (ElementRecord, PrefixElementARecord,
                                  ShortDictionaryElementRecord,
                                  ShortElementRecord)
from wcf.records.text import (
    Bytes32TextRecord, Chars32TextRecord, DoubleTextRecord, FloatTextRecord,
    StartListTextRecord, TrueTextRecord, UnicodeChars8TextRecord,
    UnicodeChars16TextRecord, UnicodeChars32TextRecord,
)


def decode(raw):
    return Record.parse(io.BytesIO(raw))


class TextRepresentations(unittest.TestCase):
    def test_float32_normative_examples(self):
        self.assertEqual('1.1', str(FloatTextRecord.parse(io.BytesIO(bytes.fromhex('cdcc8c3f')))))
        self.assertEqual('32.45', str(FloatTextRecord.parse(io.BytesIO(bytes.fromhex('cdcc0142')))))

    def test_double_special_and_exponent(self):
        for record in (FloatTextRecord, DoubleTextRecord):
            self.assertEqual('-0', str(record(-0.0)))
            self.assertEqual('NaN', str(record(float('nan'))))
            self.assertEqual('INF', str(record(float('inf'))))
            self.assertEqual('-INF', str(record(float('-inf'))))
            self.assertEqual('1E+20', str(record(1e20)))
            self.assertEqual('1E-7', str(record(1e-7)))
            self.assertEqual('1', str(record(1.0)))

    def test_shortest_roundtrip_random_ieee_bits(self):
        randomizer = random.Random(0xBF00)
        for byte_len, record_cls in ((4, FloatTextRecord), (8, DoubleTextRecord)):
            fmt = '<f' if byte_len == 4 else '<d'
            for _ in range(2500):
                original = randomizer.getrandbits(byte_len * 8).to_bytes(byte_len, 'little')
                value = struct.unpack(fmt, original)[0]
                if math.isnan(value):
                    continue
                text = str(record_cls(value))
                self.assertEqual(original, struct.pack(fmt, float(text)), (original.hex(), text))
                if 'E' in text:
                    self.assertNotIn('e', text)
                    self.assertRegex(text, r'E[+-]\d+$')

    def test_float32_minimal_significand_on_boundary(self):
        # 1.1 requires only two significant digits, even though Python stores
        # a 32-bit float in a float64 object when unpacking.
        value = struct.unpack('<f', bytes.fromhex('cdcc8c3f'))[0]
        self.assertEqual('1.1', str(FloatTextRecord(value)))

    def test_chars32_signed_positive_length(self):
        for n in (0, -1, -2147483648):
            with self.subTest(length=n), self.assertRaises(ValueError):
                decode(b'@\x01r\x9d' + struct.pack('<i', n))
        with self.assertRaises(ValueError):
            Chars32TextRecord('').to_bytes()
        self.assertEqual(b'\x9c\x01\x00\x00\x00a', Chars32TextRecord('a').to_bytes())

    def test_bytes32_signed_positive_length(self):
        for n in (0, -1, -2147483648):
            with self.subTest(length=n), self.assertRaises(ValueError):
                decode(b'@\x01r\xa3' + struct.pack('<i', n))
        with self.assertRaises(ValueError):
            Bytes32TextRecord(b'').to_bytes()
        self.assertEqual(b'\xa2\x01\x00\x00\x00a', Bytes32TextRecord(b'a').to_bytes())

    def test_decimal_reserved_bits_are_ignored(self):
        # [MS-OAUT] 2.2.26: wReserved "MUST be ignored by the recipient"
        wire = bytes.fromhex(
            '40 01 61 94 01 00 02 00 00 00 00 00 96 00 00 00 00 00 00 00 01')
        self.assertEqual('<a>1.50</a>', render_xml(decode(wire)))
        # ignored, but written back as read
        self.assertEqual(wire, dump_records(decode(wire)))
        for wire in ('40 01 61 94 00 00 1d 00' + ' 00' * 12 + ' 01',  # scale 29
                     '40 01 61 94 00 00 00 01' + ' 00' * 12 + ' 01'):  # sign 1
            with self.subTest(wire=wire), self.assertRaises(ValueError):
                decode(bytes.fromhex(wire))

    def test_float_below_one_has_a_leading_zero(self):
        # "a single zero "0" MUST precede the decimal point"
        for value, text in ((0.5, '0.5'), (-0.25, '-0.25'), (0.1, '0.1'),
                            (1e-7, '1E-7'), (100.0, '1E+2')):
            with self.subTest(value=value):
                self.assertEqual(text, str(DoubleTextRecord(value)))
                self.assertEqual(text, str(FloatTextRecord(value)))
        self.assertEqual('<a>0.5</a>', render_xml(decode(bytes.fromhex(
            '40 01 61 92 00 00 00 00 00 00 E0 3F 01'))))

    def test_unicode_chars32_uses_int32(self):
        # MC-NBFX section 3 example; the .NET reader agrees (section
        # 2.2.3.29 says MultiByteInt31, which contradicts both)
        self.assertEqual('<doc u32="32"></doc>', render_xml(decode(bytes.fromhex(
            '40 03 64 6F 63 04 03 75 33 32 BA 04 00 00 00 33 00 32 00 01'))))
        self.assertEqual('<U32>32</U32>', render_xml(decode(bytes.fromhex(
            '40 03 55 33 32 BB 04 00 00 00 33 00 32 00'))))
        for value in ('', 'abc', 'é' * 70, 'a' * 32769):
            with self.subTest(length=len(value)):
                rec = UnicodeChars32TextRecord(value)
                raw = rec.to_bytes()
                self.assertEqual(0xBA, raw[0])
                self.assertEqual(struct.pack('<i', 2 * len(value)), raw[1:5])
                self.assertEqual(value, str(UnicodeChars32TextRecord.parse(io.BytesIO(raw[1:]))))
        for raw in (b'\x03\x00\x00\x00abc', b'\xff\xff\xff\xff',
                    b'\x06\x00\x00\x00a\x00'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                UnicodeChars32TextRecord.parse(io.BytesIO(raw))

    def test_unicode_chars_odd_length_and_overflow(self):
        for record in (UnicodeChars8TextRecord, UnicodeChars16TextRecord):
            with self.subTest(record=record.__name__), self.assertRaises(ValueError):
                record.parse(io.BytesIO(b'\x03\x00a\x00'))
        with self.assertRaises(ValueError):
            UnicodeChars8TextRecord('a' * 128).to_bytes()
        with self.assertRaises(ValueError):
            UnicodeChars16TextRecord('a' * 32768).to_bytes()


class NameAndAttributeValidation(unittest.TestCase):
    def test_unqualified_attribute_requires_text(self):
        with self.assertRaises(ValueError):
            decode(bytes.fromhex('40 01 72 04 01 61 40 01 78 01'))
        for cls in (ShortAttributeRecord,):
            with self.assertRaises(ValueError):
                cls('a', ShortElementRecord('bad'))
        with self.assertRaises(ValueError):
            ShortAttributeRecord('a', None)

    def test_all_attribute_value_families(self):
        bad_value = b'\x40\x01x\x01'
        examples = (
            b'\x04\x01a',              # ShortAttribute
            b'\x05\x01a\x01b',       # Attribute
            b'\x06\x02',              # ShortDictionaryAttribute
            b'\x07\x01a\x02',        # DictionaryAttribute
            b'\x26\x01b',             # PrefixAttributeA
            b'\x0c\x02',              # PrefixDictionaryAttributeA
        )
        for header in examples:
            with self.subTest(header=header.hex()), self.assertRaises(ValueError):
                decode(b'\x40\x01r' + header + bad_value)

    def test_reject_empty_or_reserved_literal_names(self):
        for local in ('', 'xmlns'):
            for maker in (
                lambda: ShortElementRecord(local),
                lambda: ElementRecord('p', local),
                lambda: PrefixElementARecord(local),
                lambda: ShortAttributeRecord(local, TrueTextRecord()),
                lambda: AttributeRecord('p', local, TrueTextRecord()),
                lambda: PrefixAttributeARecord(local, TrueTextRecord()),
            ):
                with self.subTest(local=local, cls=maker), self.assertRaises(ValueError):
                    maker()
        for maker in (
            lambda: ElementRecord('', 'e'),
            lambda: AttributeRecord('', 'a', TrueTextRecord()),
            lambda: DictionaryXmlnsAttributeRecord('', 6),
            lambda: XmlnsAttributeRecord('', 'urn:example'),
            lambda: AttributeRecord('xmlns', 'a', TrueTextRecord()),
        ):
            with self.assertRaises(ValueError):
                maker()

    def test_reject_invalid_names_after_mutation(self):
        for maker, attribute in (
            (ShortElementRecord('a'), 'name'),
            (ShortAttributeRecord('a', TrueTextRecord()), 'name'),
            (AttributeRecord('p', 'a', TrueTextRecord()), 'prefix'),
        ):
            setattr(maker, attribute, 'xmlns')
            with self.assertRaises(ValueError):
                maker.to_bytes()
        attr = ShortAttributeRecord('a', TrueTextRecord())
        attr.value = ShortElementRecord('b')
        with self.assertRaises(ValueError):
            attr.to_bytes()

    def test_dictionary_names_checked_against_session_table(self):
        with dictionary_context({1: '', 3: 'xmlns', 5: 'widget'}):
            for index in (1, 3):
                with self.subTest(index=index), self.assertRaises(ValueError):
                    ShortDictionaryElementRecord(index)
                # checked at construction, like the element records
                for maker in (
                    lambda: ShortDictionaryAttributeRecord(index, TrueTextRecord()),
                    lambda: DictionaryAttributeRecord('p', index, TrueTextRecord()),
                    lambda: PrefixDictionaryAttributeARecord(index, TrueTextRecord()),
                ):
                    with self.assertRaises(ValueError):
                        maker()
            self.assertEqual('widget', ShortDictionaryElementRecord(5).name)
            self.assertTrue(ShortDictionaryAttributeRecord(5, TrueTextRecord()).to_bytes())

    def test_list_text_still_allowed_in_attribute(self):
        record = ShortAttributeRecord('list', StartListTextRecord([TrueTextRecord()]))
        raw = record.to_bytes()
        self.assertIsInstance(ShortAttributeRecord.parse(io.BytesIO(raw[1:])).value,
                              StartListTextRecord)


if __name__ == '__main__':
    unittest.main()
