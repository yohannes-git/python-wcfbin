"""The fast paths of the codec give the results of the general code."""

import io
import struct
import unittest
from collections import ChainMap
from unittest import mock

from wcf.datatypes import (MultiByteInt31, Utf8String, mbi31_bytes,
                           read_mbi31, read_utf8, utf8_bytes)
from wcf.dictionary import dictionary, dictionary_context, inverted_dict
from wcf.errors import WcfBinaryError
from wcf.records import (ArrayRecord, Int32TextRecord, Record,
                         ShortElementRecord, render_xml)
from wcf.records import text


class FieldTests(unittest.TestCase):

    def test_mbi31_and_utf8_writers(self):
        for value in (0, 1, 0x7F, 0x80, 0x3FFF, 0x4000, 0x1FFFFF, 0x200000,
                      0x7FFFFFFF):
            with self.subTest(value=value):
                self.assertEqual(MultiByteInt31(value).to_bytes(), mbi31_bytes(value))
                self.assertEqual(value, read_mbi31(io.BytesIO(mbi31_bytes(value))))
        for string in ('', 'a' * 127, 'a' * 128, 'é' * 64, '€' * 50000):
            with self.subTest(length=len(string)):
                self.assertEqual(Utf8String(string).to_bytes(), utf8_bytes(string))
                self.assertEqual(string, read_utf8(io.BytesIO(utf8_bytes(string))))
        for wire in (b'', b'\x80', b'\x80\x00', b'\xff\xff\xff\xff\x08'):
            with self.subTest(wire=wire), self.assertRaises(WcfBinaryError):
                read_mbi31(io.BytesIO(wire))


class DictionaryViewTests(unittest.TestCase):

    def test_lookups_agree_through_nested_chain_maps(self):
        session = ChainMap({1: 'a'}, ChainMap({3: 'b'}, {5: 'c', 2: 'shadowed'}))
        with dictionary_context(session):
            for key, value in ((1, 'a'), (3, 'b'), (5, 'c'), (2, 'Envelope')):
                self.assertEqual(value, dictionary[key])   # static ids first
                self.assertEqual(value, dictionary.get(key))
                self.assertIn(key, dictionary)
            for key in (7, -1, 'x'):
                self.assertNotIn(key, dictionary)
                self.assertIsNone(dictionary.get(key))
                with self.assertRaises(KeyError):
                    dictionary[key]
            self.assertEqual(3, inverted_dict['b'])
            self.assertEqual(2, inverted_dict.get('Envelope'))
            self.assertIsNone(inverted_dict.get('nowhere'))
        self.assertNotIn(1, dictionary)


class ArrayTests(unittest.TestCase):

    wire = (b'\x40\x01r\x03\x40\x01a\x01\x8d\x03' +
            struct.pack('<3i', 1, -2, 2 ** 31 - 1) + b'\x01')

    def decode(self, wire):
        return Record.parse(io.BytesIO(wire))

    def test_bulk_and_item_by_item_reading_agree(self):
        fast = self.decode(self.wire)
        with mock.patch.object(text._FixedSizeText, '_array_unpack', False):
            slow = self.decode(self.wire)
            self.assertEqual(render_xml(fast), render_xml(slow))
            for cut in range(len(self.wire) - 13, len(self.wire) - 1):
                with self.subTest(cut=cut), self.assertRaises(WcfBinaryError):
                    self.decode(self.wire[:cut])
        for cut in range(len(self.wire) - 13, len(self.wire) - 1):
            with self.subTest(cut=cut), self.assertRaises(WcfBinaryError):
                self.decode(self.wire[:cut])

    def test_subclasses_are_escaped(self):
        class Markup(Int32TextRecord):
            def __str__(self):
                return '<x/>'
        element = ShortElementRecord('a')
        element.childs.append(Markup(1))
        array = ArrayRecord(ShortElementRecord('i'), [Markup(1), Markup(2)], [])
        self.assertEqual('<a>&lt;x/&gt;</a><i>&lt;x/&gt;</i><i>&lt;x/&gt;</i>',
                         render_xml([element, array]))


if __name__ == '__main__':
    unittest.main()
