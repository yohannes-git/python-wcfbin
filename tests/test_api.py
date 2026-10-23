"""Record constructors: exact signatures and types, no silent coercion."""

import io
import unittest

from wcf.records import (render_xml, ShortElementRecord, ElementRecord,
                         ShortDictionaryElementRecord, DictionaryElementRecord,
                         CommentRecord, XmlnsAttributeRecord,
                         ShortXmlnsAttributeRecord, ZeroTextRecord,
                         Chars8TextRecord, UnicodeChars8TextRecord,
                         Bytes8TextRecord, Bytes32TextRecord,
                         DatetimeTextRecord)


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

    def test_parse_returns_the_subclass(self):
        class MyDateTime(DatetimeTextRecord):
            pass
        self.assertIs(MyDateTime, type(MyDateTime.parse(io.BytesIO(b'\x00' * 8))))


if __name__ == '__main__':
    unittest.main()
