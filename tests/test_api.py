"""Record constructors: exact signatures and types, no silent coercion."""

import io
import unittest

from wcf.records import (render_xml, ShortElementRecord, ElementRecord,
                         ShortDictionaryElementRecord, DictionaryElementRecord,
                         CommentRecord, XmlnsAttributeRecord,
                         ShortXmlnsAttributeRecord, ZeroTextRecord,
                         Chars8TextRecord, UnicodeChars8TextRecord,
                         Bytes8TextRecord, Bytes32TextRecord,
                         DatetimeTextRecord, ShortAttributeRecord,
                         AttributeRecord, ShortDictionaryAttributeRecord,
                         PrefixDictionaryElementSRecord, PrefixAttributeKRecord,
                         TrueTextRecord)


class ConstructorTests(unittest.TestCase):

    def test_extra_arguments_are_refused(self):
        # they used to be ignored, or to change the record type
        for make in (lambda: ShortElementRecord('s', 'Envelope'),
                     lambda: ElementRecord('s', 'Envelope', 'x'),
                     lambda: ShortDictionaryElementRecord(2, 4),
                     lambda: DictionaryElementRecord('s', 2, 4),
                     lambda: XmlnsAttributeRecord('p', 'urn:u', 0x05),
                     lambda: ShortXmlnsAttributeRecord('urn:u', 0x99),
                     lambda: CommentRecord('a', 'b'),
                     lambda: ZeroTextRecord(0x42)):
            with self.assertRaises(TypeError):
                make()

    def test_dictionary_element_name_follows_its_index(self):
        for element in (ShortDictionaryElementRecord(2),
                        DictionaryElementRecord('s', 2)):
            element.index = 8
            self.assertEqual('Header', element.name)
            self.assertIn('Header', render_xml([element]))
            self.assertEqual(element.to_bytes()[-1], 8)

    def test_value_types(self):
        for make in (lambda: Chars8TextRecord(None),
                     lambda: Chars8TextRecord(b'ab'),
                     lambda: UnicodeChars8TextRecord(5),
                     lambda: Bytes8TextRecord('abc'),
                     lambda: Bytes32TextRecord(5)):
            with self.assertRaises(TypeError):
                make()
        self.assertEqual(b'\x9e\x02ab', Bytes8TextRecord(bytearray(b'ab')).to_bytes())

    def test_replaced_record_class_is_used_everywhere(self):
        # no cache of the record types: a class replaced in the registry
        # decodes element content and attribute values alike
        from wcf.records import Record

        class MyChars(Chars8TextRecord):
            pass
        Record.parse(io.BytesIO(b'\x40\x01a\x98\x01x\x01'))  # warm up
        original = Record.records[0x98]
        Record.records[0x98] = MyChars
        try:
            element = Record.parse(io.BytesIO(
                b'\x40\x01a\x04\x01b\x98\x01v\x98\x01x\x01'))[0]
            self.assertIs(MyChars, type(element.childs[0]))
            self.assertIs(MyChars, type(element.attributes[0].value))
        finally:
            Record.records[0x98] = original

    def test_letter_prefix_records(self):
        from wcf.records import (PrefixElementARecord, PrefixElementRecord,
                                 PrefixDictionaryElementRecord, PrefixAttributeRecord,
                                 PrefixDictionaryAttributeRecord, TrueTextRecord)
        record = PrefixElementARecord('x')
        self.assertEqual('a', record.prefix)
        with self.assertRaises(AttributeError):
            record.prefix = 'b'  # the letter is the record type
        for base, args in ((PrefixElementRecord, ('x',)),
                           (PrefixDictionaryElementRecord, (2,)),
                           (PrefixAttributeRecord, ('x', TrueTextRecord())),
                           (PrefixDictionaryAttributeRecord, (2, TrueTextRecord()))):
            with self.subTest(base=base.__name__), self.assertRaises(TypeError):
                base(*args)

    def test_xmlns_qname(self):
        self.assertEqual('xmlns', ShortXmlnsAttributeRecord('urn:a').qname)
        self.assertEqual('xmlns:a', XmlnsAttributeRecord('a', 'urn:a').qname)

    def test_qualified_names(self):
        value = TrueTextRecord()
        for record, qname in ((ShortElementRecord('a'), 'a'),
                              (ElementRecord('p', 'a'), 'p:a'),
                              (ShortDictionaryElementRecord(2), 'Envelope'),
                              (PrefixDictionaryElementSRecord(2), 's:Envelope'),
                              (ShortAttributeRecord('b', value), 'b'),
                              (AttributeRecord('p', 'b', value), 'p:b'),
                              (ShortDictionaryAttributeRecord(2, value), 'Envelope'),
                              (PrefixAttributeKRecord('b', value), 'k:b')):
            with self.subTest(record=type(record).__name__):
                self.assertEqual(qname, record.qname)

    def test_xmlns_namespace_and_prefix(self):
        for args in ((b'urn:a',), ('a', b'urn:a'), ('a', None)):
            with self.subTest(args=args), self.assertRaises(TypeError):
                (XmlnsAttributeRecord if len(args) == 2 else ShortXmlnsAttributeRecord)(*args)
        # "name" is the prefix, as the former attribute of that name
        self.assertEqual('a', XmlnsAttributeRecord('a', 'urn:a').name)

    def test_record_type_registered_once(self):
        from wcf.records import Record

        class Other(Record):
            type = ShortElementRecord.type
        with self.assertRaisesRegex(RuntimeError, 'registered twice'):
            Record.add_records((Other,))
        self.assertIs(ShortElementRecord, Record.records[ShortElementRecord.type])

    def test_parse_returns_the_subclass(self):
        class MyDateTime(DatetimeTextRecord):
            pass
        self.assertIs(MyDateTime, type(MyDateTime.parse(io.BytesIO(b'\x00' * 8))))



class DatatypeTests(unittest.TestCase):

    def test_multibyteint31_and_utf8string(self):
        from wcf.datatypes import MultiByteInt31, Utf8String
        self.assertEqual('300', str(MultiByteInt31(300)))
        self.assertEqual('é', Utf8String('é'.encode()).value)
        self.assertEqual(b'\x02\xc3\xa9', Utf8String('é'.encode()).to_bytes())

    def test_session_dictionary_view(self):
        # the static table, then the session strings that it does not have
        from wcf.dictionary import dictionary, dictionary_context
        static = len(dictionary)
        self.assertEqual(static, len(list(dictionary)))
        with dictionary_context({1: 'x', 3: 'y'}):
            self.assertEqual(static + 2, len(dictionary))
            self.assertEqual([1, 3], [k for k in dictionary if k % 2])
            self.assertEqual('y', dictionary[3])
        self.assertEqual(static, len(dictionary))

    def test_local_offset_where_the_host_cannot_compute_it(self):
        # time.localtime() refuses a date beyond the platform's time_t:
        # the current offset of the host is used
        from unittest import mock
        from wcf.records import text
        real = text.time.localtime
        calls = []

        def localtime(*args):
            calls.append(args)
            if args:
                raise OverflowError('timestamp out of range')
            return real()
        with mock.patch.object(text.time, 'localtime', localtime):
            offset = text._local_utc_offset(0)
        self.assertEqual(real().tm_gmtoff * 10 ** 7, offset)
        self.assertEqual(2, len(calls))


if __name__ == '__main__':
    unittest.main()
