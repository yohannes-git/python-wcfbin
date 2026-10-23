"""Record constructors: exact signatures and types, no silent coercion."""

import io
import unittest

from wcf.records import (
    render_xml, dump_records, ShortElementRecord, ElementRecord,
    ShortDictionaryElementRecord, DictionaryElementRecord, CommentRecord,
    XmlnsAttributeRecord, ShortXmlnsAttributeRecord, ZeroTextRecord,
    Chars8TextRecord, UnicodeChars8TextRecord, Bytes8TextRecord,
    Bytes32TextRecord, DatetimeTextRecord)


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

    def test_parse_returns_the_subclass(self):
        class MyDateTime(DatetimeTextRecord):
            pass
        self.assertIs(MyDateTime, type(MyDateTime.parse(io.BytesIO(b'\x00' * 8))))


if __name__ == '__main__':
    unittest.main()
