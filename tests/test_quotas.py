"""Decoding quotas (MC-NBFX and MC-NBFSE section 4)."""

import io
import random
import struct
import unittest

from wcf.datatypes import Decimal, MultiByteInt31
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
        fp = io.BytesIO(wire)
        with dictionary_context({1: 'x' * 60000}):
            with self.assertRaisesRegex(ValueError, 'characters'):
                Record.parse(fp)
            # refused after 280 references (16 MiB), not at the end
            self.assertLess(fp.tell(), 1000)
            records = parse(b'\x40\x01a' + b'\xaa\x01' * 10 + b'\x01')
            self.assertEqual(600007, len(render_xml(records)))

    def test_static_dictionary_amplification(self):
        # 0x48: "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
        wire = b'\x40\x01a' + b'\xaa\x48' * 4000 + b'\x01'
        with self.assertRaisesRegex(ValueError, 'characters'):
            parse(wire, Quotas(max_chars=100000))

    def test_array_is_charged_before_its_items_are_read(self):
        # 2^30 Int64 items announced, 8 bytes given
        wire = (b'\x40\x01r\x03\x40\x01a\x01\x8f' +
                MultiByteInt31(1 << 30).to_bytes() + b'\x00' * 8 + b'\x01')
        fp = io.BytesIO(wire)
        with self.assertRaisesRegex(ValueError, 'records'):
            Record.parse(fp)
        # refused before reading any item
        self.assertEqual(len(wire) - 9, fp.tell())
        with self.assertRaisesRegex(ValueError, 'characters'):
            parse(wire, Quotas(max_records=None))

    def test_array_attributes(self):
        # attributes of an Array are charged as they are read: 100,000 of
        # them without an EndElement must not all be allocated first
        wire = b'\x40\x01r\x03\x42\x02' + b'\x06\x02\x86' * 100000
        with self.assertRaisesRegex(ValueError, 'records'):
            parse(wire, Quotas(max_records=1000))

    def test_array_attribute_list_counts_for_every_item(self):
        # a list-valued attribute of an Array is rendered with every item:
        # 1,000 list items x 1,000 array items, 3 KB of input
        wire = (b'\x40\x01r\x03\x40\x01a\x04\x01b\xa4' + b'\x98\x01x' * 1000 +
                b'\xa6\x01\x8d' + MultiByteInt31(1000).to_bytes() +
                b'\x00' * 4000 + b'\x01')
        with self.assertRaisesRegex(ValueError, 'characters|records'):
            parse(wire, Quotas(max_chars=1000000, max_records=None))
        with self.assertRaisesRegex(ValueError, 'records'):
            parse(wire)
        records = parse(wire, NO_QUOTAS)
        self.assertGreater(len(render_xml(records)), 2000000)

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

    def test_announced_lengths_are_not_allocated(self):
        # MC-NBFX 4: an 8-byte document announcing 2 GiB must not make a
        # file object allocate them
        class Spy(io.BytesIO):
            largest = 0

            def read(self, size=-1):
                Spy.largest = max(Spy.largest, size)
                return super().read(size)
        for wire in (b'\x40\x01a\x9c\xff\xff\xff\x7f',   # Chars32Text
                     b'\x40\x01a\xa2\xff\xff\xff\x7f',   # Bytes32Text
                     b'\x40\x01a\xba\xff\xff\xff\x7f',   # UnicodeChars32Text
                     b'\x40\xff\xff\xff\xff\x07',        # String
                     b'\x02\xff\xff\xff\xff\x07'):       # Comment
            with self.subTest(wire=wire), self.assertRaises(ValueError):
                Record.parse(Spy(wire))
        self.assertLessEqual(Spy.largest, 1 << 16)
        big = b'\x40\x01a\x9d' + struct.pack('<i', 300000) + b'x' * 300000
        self.assertEqual(300000, len(parse(big)[0].childs[0].value))

    def test_short_reads(self):
        # a raw stream may return fewer bytes than asked for
        class Trickle(io.RawIOBase):
            def __init__(self, data):
                self.fp = io.BytesIO(data)

            def readable(self):
                return True

            def readinto(self, buffer):
                data = self.fp.read(min(len(buffer), 3))
                buffer[:len(data)] = data
                return len(data)
        big = 'x' * 70000
        wire = (b'\x40\x01a\x98\x0a0123456789' + b'\x9c' +
                struct.pack('<i', len(big)) + big.encode() + b'\x01')
        self.assertEqual('<a>0123456789%s</a>' % big, render_xml(Record.parse(Trickle(wire))))
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            Record.parse(Trickle(wire[:20]))

    def test_quotas_are_immutable(self):
        import dataclasses
        from wcf.records import DEFAULT_QUOTAS
        with self.assertRaises(dataclasses.FrozenInstanceError):
            DEFAULT_QUOTAS.max_depth = None

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
            DatetimeTextRecord(3155378975999999999 - 15 * 3600 * 10 ** 7, 2),
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

    def test_max_chars_is_the_longest_rendering(self):
        # an upper bound that is not reached would charge the quotas more
        # than the document represents
        from wcf.records import (Record, Text, ZeroTextRecord, OneTextRecord,
                                 TrueTextRecord, FalseTextRecord, EmptyTextRecord,
                                 EndListTextRecord)
        from tests.support import local_times
        longest = [
            Int8TextRecord(-128), Int16TextRecord(-32768), Int32TextRecord(-2 ** 31),
            Int64TextRecord(-2 ** 63), UInt64TextRecord(2 ** 64 - 1), BoolTextRecord(False),
            ZeroTextRecord(), OneTextRecord(), TrueTextRecord(), FalseTextRecord(),
            EmptyTextRecord(),
            DecimalTextRecord(Decimal(True, 2 ** 32 - 1, 2 ** 64 - 1, 28)),
            FloatTextRecord(struct.unpack('<f', struct.pack('<I', 0xa9e821a4))[0]),  # -1.03087054E-13
            DoubleTextRecord(-2.2250738585072014e-308),
            UniqueIdTextRecord('urn:uuid:33221100-5544-7766-8899-aabbccddeeff'),
            UuidTextRecord('33221100-5544-7766-8899-aabbccddeeff'),
            TimeSpanTextRecord(-2 ** 63)]
        lengths = {type(r): len(str(r)) for r in longest}
        lengths[EndListTextRecord] = 0  # renders nothing, it closes a list
        # a local time with its offset, on a host 14 hours ahead of UTC
        max_ticks = 3155378976000000000
        local, = local_times('XST-14', [max_ticks - 1 - 14 * 3600 * 10 ** 7])
        self.assertEqual('9999-12-31T23:59:59.9999999+14:00', local)
        lengths[DatetimeTextRecord] = len(local)
        fixed = {cls for cls in Record.records.values()
                 if issubclass(cls, Text) and cls.max_chars is not None}
        self.assertEqual(fixed, set(lengths))
        for cls in fixed:
            with self.subTest(record=cls.__name__):
                self.assertEqual(cls.max_chars, lengths[cls])

    def test_cost_of_a_document(self):
        # what max_chars counts: the names (twice for an element), the
        # values, comments, xmlns prefixes and namespaces, one separator
        # per list item, every array item with its element and attributes
        # (the attributes of an array also once as read)
        for wire, cost in (
                (b'\x40\x01a\x99\x03xyz', 2 + 3),                       # <a>xyz</a>
                (b'\x41\x01p\x01a\x01', 2 * 3),                         # <p:a></p:a>
                (b'\x40\x01a\x02\x03abc\x01', 2 + 3),                  # <!--abc-->
                (b'\x40\x01a\x05\x01p\x01b\x98\x01v\x01', 2 + 3 + 1),   # p:b="v"
                (b'\x40\x01a\x09\x01p\x05urn:x\x01', 2 + 1 + 5),        # xmlns:p="urn:x"
                (b'\x40\x01a\xa4\x98\x01x\x98\x02yz\xa6\x01', 2 + 2 + 3),  # "x yz"
                (b'\x40\x01a\x89\x80', 2 + 4),                          # Int8: up to "-128"
                (b'\x40\x01a\x9f\x04abcd', 2 + 8),                      # base64 "YWJjZA=="
                (b'\x03\x40\x01a\x01\x8d\x02' + b'\x00' * 8, 2 * (2 + 11)),
                (b'\x03\x40\x03abc\x01\x8d\x02' + b'\x00' * 8, 2 * (6 + 11)),
                (b'\x03\x40\x01a\x04\x01b\x98\x01v\x01\x8d\x02' + b'\x00' * 8,
                 2 + 2 * (2 + 11 + 2))):
            with self.subTest(wire=wire):
                parse(wire, Quotas(max_chars=cost))
                with self.assertRaisesRegex(ValueError, 'characters'):
                    parse(wire, Quotas(max_chars=cost - 1))

    def test_records_of_a_document(self):
        # what max_records counts: every element, attribute, text, comment,
        # list item and array item
        for wire, records in (
                (b'\x40\x01a\x01', 1),
                (b'\x40\x01a\x99\x03xyz', 2),
                (b'\x40\x01a\x02\x03abc\x01', 2),
                (b'\x40\x01a\x04\x01b\x98\x01v\x01', 3),
                (b'\x40\x01a\xa4\x98\x01x\x98\x02yz\xa6\x01', 4)):
            with self.subTest(wire=wire):
                parse(wire, Quotas(max_records=records))
                with self.assertRaisesRegex(ValueError, 'records'):
                    parse(wire, Quotas(max_records=records - 1))

    def test_bytes_char_count_is_the_base64_length(self):
        from wcf.records import Bytes8TextRecord
        for n in range(10):
            record = Bytes8TextRecord(bytes(n))
            self.assertEqual(len(str(record)), record.char_count(), n)


if __name__ == '__main__':
    unittest.main()
