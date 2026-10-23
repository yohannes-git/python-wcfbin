"""Decoding quotas (MC-NBFX and MC-NBFSE section 4)."""

import io
import random
import struct
import time
import unittest

from wcf.datatypes import Decimal, MultiByteInt31, Utf8String
from wcf.dictionary import dictionary_context
from wcf.records import (
    Record, Quotas, NO_QUOTAS, render_xml, dump_records,
    Int8TextRecord, Int16TextRecord, Int32TextRecord, Int64TextRecord,
    UInt64TextRecord, FloatTextRecord, DoubleTextRecord, DecimalTextRecord,
    DatetimeTextRecord, UniqueIdTextRecord, UuidTextRecord,
    TimeSpanTextRecord, BoolTextRecord)


def parse(wire, quotas=Quotas()):
    return Record.parse(io.BytesIO(wire), quotas)


class QuotaTests(unittest.TestCase):

    def test_depth(self):
        wire = b'\x40\x01a' * 10 + b'\x01' * 10
        parse(wire, Quotas(max_depth=10))
        with self.assertRaisesRegex(ValueError, 'nested deeper'):
            parse(wire, Quotas(max_depth=9))
        # far below the interpreter recursion limit of render_xml()
        deep = b'\x40\x01a' * 5000 + b'\x01' * 5000
        with self.assertRaises(ValueError):
            parse(deep)
        records = parse(deep, NO_QUOTAS)
        self.assertEqual(5000, render_xml(records).count('<a>'))
        self.assertEqual(deep, dump_records(records))

    def test_records(self):
        wire = b'\x40\x01r' + b'\x40\x01a\x01' * 99 + b'\x01'
        parse(wire, Quotas(max_records=100))
        with self.assertRaisesRegex(ValueError, 'records'):
            parse(wire, Quotas(max_records=99))

    def test_dictionary_amplification(self):
        # two bytes per reference to a 60 KiB session string: 100 KB of
        # input would render as 1.2 GB
        refs = 50000
        wire = b'\x40\x01a' + b'\xaa\x01' * refs + b'\x01'
        start = time.monotonic()
        with dictionary_context({1: 'x' * 60000}):
            with self.assertRaisesRegex(ValueError, 'characters'):
                parse(wire)
            records = parse(b'\x40\x01a' + b'\xaa\x01' * 10 + b'\x01')
            self.assertEqual(600007, len(render_xml(records)))
        self.assertLess(time.monotonic() - start, 2)

    def test_static_dictionary_amplification(self):
        # 0x48: "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
        wire = b'\x40\x01a' + b'\xaa\x48' * 4000 + b'\x01'
        with self.assertRaisesRegex(ValueError, 'characters'):
            parse(wire, Quotas(max_chars=100000))

    def test_array_is_charged_before_its_items_are_read(self):
        # 2^30 Int64 items announced, 8 bytes given
        wire = (b'\x40\x01r\x03\x40\x01a\x01\x8f' +
                MultiByteInt31(1 << 30).to_bytes() + b'\x00' * 8 + b'\x01')
        start = time.monotonic()
        with self.assertRaisesRegex(ValueError, 'records'):
            parse(wire)
        self.assertLess(time.monotonic() - start, 1)
        with self.assertRaisesRegex(ValueError, 'characters'):
            parse(wire, Quotas(max_records=None))

    def test_array_attributes(self):
        # attributes of an Array are charged as they are read: 100,000 of
        # them without an EndElement must not all be allocated first
        wire = b'\x40\x01r\x03\x42\x02' + b'\x06\x02\x86' * 100000
        with self.assertRaisesRegex(ValueError, 'records'):
            parse(wire, Quotas(max_records=1000))

    def test_array_in_attribute_position(self):
        # used to recurse without bound (RecursionError)
        for wire in (b'\x03\x40\x01a' * 5000, b'\x03\x42\x02' * 1000,
                     b'\x40\x01r\x03\x40\x01a\x02\x01x\x01'):
            with self.subTest(wire=wire[:8]), self.assertRaisesRegex(
                    ValueError, 'ArrayRecord attribute'):
                parse(wire, NO_QUOTAS)

    def test_list_items(self):
        wire = b'\x40\x01a\xa4' + b'\x80' * 1000 + b'\xa6\x01'
        with self.assertRaisesRegex(ValueError, 'records'):
            parse(wire, Quotas(max_records=500))
        self.assertEqual(1999, len(render_xml(parse(wire))) - len('<a></a>'))

    def test_quotas_are_per_document(self):
        wire = b'\x40\x01a\x01'
        quotas = Quotas(max_records=1)
        for _ in range(3):
            parse(wire, quotas)

    def test_max_chars_bounds_the_rendering(self):
        rng = random.Random(7)
        samples = [
            Int8TextRecord(-128), Int16TextRecord(-32768),
            Int32TextRecord(-2 ** 31), Int64TextRecord(-2 ** 63),
            UInt64TextRecord(2 ** 64 - 1), BoolTextRecord(False),
            DecimalTextRecord(Decimal(True, 2 ** 32 - 1, 2 ** 64 - 1, 0)),
            DecimalTextRecord(Decimal(True, 2 ** 32 - 1, 2 ** 64 - 1, 28)),
            DecimalTextRecord(Decimal(True, 0, 1, 28)),
            DatetimeTextRecord(3155378975999999999, 1),
            DatetimeTextRecord(3155378975999999999, 2),
            UniqueIdTextRecord('urn:uuid:33221100-5544-7766-8899-aabbccddeeff'),
            UuidTextRecord('33221100-5544-7766-8899-aabbccddeeff'),
            TimeSpanTextRecord(-2 ** 63), TimeSpanTextRecord(2 ** 63 - 1)]
        for _ in range(5000):
            bits = rng.getrandbits(64)
            samples.append(DoubleTextRecord(struct.unpack('<d', struct.pack('<Q', bits))[0]))
            samples.append(FloatTextRecord(struct.unpack('<f', struct.pack('<I', bits >> 32))[0]))
        for record in samples:
            with self.subTest(record=record):
                self.assertLessEqual(len(str(record)), record.max_chars)


if __name__ == '__main__':
    unittest.main()
