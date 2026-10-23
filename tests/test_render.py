"""render_xml(): the XML text must have the structure of the records."""

import io
import unittest
from xml.etree import ElementTree as ET

from wcf.datatypes import Utf8String
from wcf.dictionary import dictionary_context
from wcf.records import (
    Record, render_xml, CommentRecord, ShortElementRecord, ElementRecord,
    ShortAttributeRecord, AttributeRecord, XmlnsAttributeRecord,
    ShortDictionaryElementRecord, Chars8TextRecord)


def render(wire):
    return render_xml(Record.parse(io.BytesIO(wire)))


class RenderInjectionTests(unittest.TestCase):
    """A name or comment that is not representable must not be written
    as markup: 'a b="c"' as an element name would add an attribute,
    '--><x/><!--' in a comment an element."""

    def test_element_name(self):
        for name in ('x evil="1"', 'a>b', 'a/', '1a', 'a:b', '-a', 'a b'):
            wire = b'\x40' + Utf8String(name).to_bytes() + b'\x01'
            with self.subTest(name=name), self.assertRaises(ValueError):
                render(wire)

    def test_prefixes_and_attribute_names(self):
        value = Chars8TextRecord('v')
        for record in (ElementRecord('p q', 'a'),
                       ShortElementRecord('a')):
            if isinstance(record, ShortElementRecord):
                record.attributes.append(ShortAttributeRecord('b c="d"', value))
            with self.subTest(record=record), self.assertRaises(ValueError):
                render_xml([record])
        element = ShortElementRecord('a')
        element.attributes.append(AttributeRecord('p"', 'n', value))
        with self.assertRaises(ValueError):
            render_xml([element])
        element = ShortElementRecord('a')
        element.attributes.append(XmlnsAttributeRecord('p q', 'urn:x'))
        with self.assertRaises(ValueError):
            render_xml([element])

    def test_session_dictionary_name(self):
        with dictionary_context({1: 'a b="c"'}), self.assertRaises(ValueError):
            render_xml([ShortDictionaryElementRecord(1)])

    def test_comment(self):
        for comment in ('--><injected/><!--', 'a--b', 'end-', 'a\x00b',
                        'a\rb', '\ufffe'):
            with self.subTest(comment=comment), self.assertRaises(ValueError):
                render_xml([CommentRecord(comment)])
        self.assertEqual('<!--a-b c-->', render_xml([CommentRecord('a-b c')]))

    def test_valid_names(self):
        self.assertEqual('<é.x-1 _a="v"></é.x-1>', render(
            b'\x40' + Utf8String('é.x-1').to_bytes() +
            b'\x04\x02_a\x98\x01v\x01'))


class RenderEscapingTests(unittest.TestCase):

    def test_hand_made_records_are_refused_or_escaped(self):
        from wcf.datatypes import Decimal
        from wcf.records import (Int32TextRecord, UInt64TextRecord,
                                 DecimalTextRecord, DoubleTextRecord,
                                 DatetimeTextRecord, TimeSpanTextRecord,
                                 BoolTextRecord)
        # a value of the wrong type is refused when the record is built
        for make in (lambda: Int32TextRecord('<x/>'), lambda: Int32TextRecord(True),
                     lambda: UInt64TextRecord('<x/>'), lambda: DoubleTextRecord('1'),
                     lambda: DecimalTextRecord('<x/>'), lambda: BoolTextRecord(1),
                     lambda: DatetimeTextRecord('<x/>', 0),
                     lambda: TimeSpanTextRecord('<x/>')):
            with self.assertRaises(TypeError):
                make()
        self.assertEqual('1.5', str(DecimalTextRecord(Decimal(False, 0, 15, 1))))

        # a subclass may write anything: it is escaped (the fast path of
        # render_xml() only applies to the exact classes)
        class Markup(Int32TextRecord):
            def __str__(self):
                return '<x/>'
        element = ShortElementRecord('a')
        element.childs.append(Markup(1))
        self.assertEqual('<a>&lt;x/&gt;</a>', render_xml([element]))

    def test_microsoft_character_escaping_example(self):
        # MC-NBFX 2.2.3.13.1: { 0x22, 0x26, 0x3C, 0x3E, 0x27, 0x00 }
        chars = b'\x98\x06"&<>\'\x00'
        self.assertEqual('<a>"&amp;&lt;&gt;\'&#0;</a>',
                         render(b'\x40\x01a' + chars + b'\x01'))
        self.assertEqual('<a b="&quot;&amp;&lt;&gt;\'&#0;"></a>',
                         render(b'\x40\x01a\x04\x01b' + chars + b'\x01'))

    def test_characters_not_legal_in_xml(self):
        self.assertEqual('<a>&#1;&#31;&#65534;</a>',
                         render(b'\x40\x01a\x99\x05\x01\x1f\xef\xbf\xbe'))

    def test_whitespace_survives_an_xml_parser(self):
        text = 'a\r\nb\rc\td\ne'
        value = Utf8String(text).to_bytes()
        xml = render(b'\x40\x01a\x04\x01b\x98' + value + b'\x99' + value)
        root = ET.fromstring(xml)
        self.assertEqual(text, root.text)
        self.assertEqual(text, root.get('b'))


if __name__ == '__main__':
    unittest.main()
