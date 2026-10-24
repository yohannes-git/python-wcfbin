"""XML to records: every invalid input is a ValueError, raised early."""

import io
import unittest

from wcf.datatypes import Decimal
from wcf.records import (Record, dump_records, render_xml, Chars32TextRecord,
                         Bytes32TextRecord)
from wcf.session import BinaryXmlSession
from wcf.xml2records import XMLParser


class XmlInputTests(unittest.TestCase):

    def test_malformed_xml(self):
        for xml in ('<unclosed>', '<a></b>', '<a b="1" b="2"/>', 'text',
                    '<a>&undefined;</a>', '<a>\x01</a>'):
            with self.subTest(xml=xml):
                with self.assertRaises(ValueError):
                    XMLParser.parse(xml)
                with self.assertRaises(ValueError):
                    BinaryXmlSession().encode_xml(xml)

    def test_standard_library_errors_are_converted(self):
        # binascii.Error of a base64 override, UnicodeDecodeError of a
        # StringTable, unknown dictionary ids
        from wcf.errors import WcfBinaryError
        from wcf.dictionary import UnknownDictionaryId
        with self.assertRaises(WcfBinaryError):
            XMLParser.parse('<b>@@@</b>', type_overrides={'/b': 'base64'})
        with self.assertRaises(WcfBinaryError):
            BinaryXmlSession().parse_document(b'\x02\x01\xff\x42\x01\x01')
        with self.assertRaises(WcfBinaryError):
            Record.parse(io.BytesIO(b'\x40\x01a\x99\x01\xff'))
        with self.assertRaisesRegex(UnknownDictionaryId, 'dictionary id 1'):
            Record.parse(io.BytesIO(b'\x42\x01\x01'))

    def test_encoding_errors(self):
        from wcf.errors import WcfBinaryError
        from wcf.records import (ShortElementRecord, Chars8TextRecord,
                                 CommentRecord)
        for element in (ShortElementRecord('a\udc00'), ShortElementRecord('a')):
            if element.name == 'a':
                element.childs.append(Chars8TextRecord('\ud800'))
            with self.assertRaises(WcfBinaryError):
                dump_records([element])
        with self.assertRaises(WcfBinaryError):
            BinaryXmlSession().encode_records([ShortElementRecord('a\udc00')])
        with self.assertRaises(TypeError):
            CommentRecord(b'x')
        # None means the default quotas, as for BinaryXmlSession
        self.assertEqual(1, len(Record.parse(io.BytesIO(b'\x40\x01a\x01'), None)))

    def test_names_must_be_ncnames(self):
        # a non namespace-aware parser takes "b:c" as the local name
        for xml in ('<a:b:c xmlns:a="urn:a"/>',
                    '<r xmlns:a="urn:a" a:b:c="1"/>'):
            with self.subTest(xml=xml), self.assertRaises(ValueError):
                XMLParser.parse(xml)

    def test_undeclared_prefix(self):
        for xml in ('<p:a/>', '<a p:b="1"/>', '<r xmlns:p="urn:p"><p:a/><q:b/></r>'):
            for types in (None, {'/{urn:p}a': 'int32'}):
                with self.subTest(xml=xml, types=types):
                    with self.assertRaisesRegex(ValueError, 'Undeclared XML namespace prefix'):
                        XMLParser.parse(xml, type_overrides=types)

    def test_inputs(self):
        # str, bytes and file objects; anything else is a wrong use
        for data in ('<a>1</a>', b'<a>1</a>', io.StringIO('<a>1</a>'), io.BytesIO(b'<a>1</a>')):
            with self.subTest(data=type(data).__name__):
                self.assertEqual('<a>1</a>', render_xml(XMLParser.parse(data)))
        with self.assertRaises(TypeError):
            XMLParser.parse(42)
        parser = XMLParser()
        parser.feed('<a/>')
        parser.close()
        with self.assertRaisesRegex(ValueError, 'closed'):
            parser.feed('<b/>')

    def test_empty_prefix(self):
        # ":a" is not a qualified name, the colon is not dropped
        for xml in ('<:a xmlns="urn:x"/>', '<a xmlns="urn:x" :b="1"/>'):
            with self.subTest(xml=xml), self.assertRaises(ValueError):
                XMLParser.parse(xml)

    def test_typed_literals_are_xml_schema_literals(self):
        # only XML whitespace around a value, only ASCII digits, as .NET's
        # XmlConvert: Unicode spaces and digits of other scripts are refused
        uuid = '33221100-5544-7766-8899-aabbccddeeff'
        for kind, text in (('double', '\u0661\u0662'), ('int32', '\u0661'),
                           ('int32', '12\u3000'), ('int32', '\xa012'),
                           ('decimal', '1\u3000'), ('bool', 'true\u2003'),
                           ('base64', 'AA\u3000AA'),
                           ('uuid', '\u0663' + uuid[1:]),
                           ('uniqueid', 'urn:uuid:\u0663' + uuid[1:])):
            with self.subTest(kind=kind, text=text), self.assertRaises(ValueError):
                XMLParser.parse('<v>%s</v>' % text, type_overrides={'/v': kind})
        for kind, text, value in (('int32', ' \t12\n', 12), ('double', ' 1.5 ', 1.5),
                                  ('bool', ' true ', True),
                                  ('base64', ' AA\tA\nA ', b'\x00\x00\x00')):
            with self.subTest(kind=kind, text=text):
                records = XMLParser.parse('<v>%s</v>' % text, type_overrides={'/v': kind})
                self.assertEqual(value, records[0].childs[0].value)
        records = XMLParser.parse('<v> %s </v>' % uuid, type_overrides={'/v': 'uuid'})
        self.assertEqual(uuid, str(records[0].childs[0]))
        records = XMLParser.parse('<v>urn:uuid:%s</v>' % uuid.upper(),
                                  type_overrides={'/v': 'uniqueid'})
        self.assertEqual('urn:uuid:' + uuid, str(records[0].childs[0]))

    def test_typed_literals(self):
        import math
        from wcf.records import BoolTextRecord, FloatTextRecord, DoubleTextRecord, Chars8TextRecord
        for kind, text, cls, value in (('bool', 'false', BoolTextRecord, False),
                                       ('bool', ' 0 ', BoolTextRecord, False),
                                       ('bool', 'true', BoolTextRecord, True),
                                       ('text', '8.0', Chars8TextRecord, '8.0'),
                                       ('string', ' 8.0 ', Chars8TextRecord, ' 8.0 '),
                                       ('float', 'INF', FloatTextRecord, math.inf),
                                       ('double', '-INF', DoubleTextRecord, -math.inf)):
            with self.subTest(kind=kind, text=text):
                record = XMLParser.parse('<v>%s</v>' % text, type_overrides={'/v': kind})[0].childs[0]
                self.assertIs(cls, type(record))
                self.assertEqual(value, record.value)
        for kind in ('float', 'double'):
            record = XMLParser.parse('<v>NaN</v>', type_overrides={'/v': kind})[0].childs[0]
            self.assertTrue(math.isnan(record.value))
        for text in ('False', 'yes', '2'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                XMLParser.parse('<v>%s</v>' % text, type_overrides={'/v': 'bool'})

    def test_uuid_literals(self):
        # what uuid.UUID() takes but the records would not render
        uuid = '33221100-5544-7766-8899-aabbccddeeff'
        for kind, text in (('uuid', '3322110_' + uuid[8:]), ('uuid', '+3221100' + uuid[8:]),
                           ('uuid', '0x221100' + uuid[8:]), ('uuid', '{%s}' % uuid),
                           ('uuid', uuid.replace('-', '')), ('uuid', 'urn:uuid:' + uuid),
                           ('uuid', '3322-1100-5544-7766-8899aabbccddeeff'),
                           ('uniqueid', uuid), ('uniqueid', 'urn:uuid:{%s}' % uuid)):
            with self.subTest(kind=kind, text=text), self.assertRaises(ValueError):
                XMLParser.parse('<v>%s</v>' % text, type_overrides={'/v': kind})

    def test_decimal_type(self):
        types = {'/d': 'decimal'}
        for text, scale, rendered in (('1.50', 2, '1.50'), ('-.5', 1, '-0.5'),
                                      ('79228162514264337593543950335', 0,
                                       '79228162514264337593543950335')):
            with self.subTest(text=text):
                records = XMLParser.parse('<d>%s</d>' % text, type_overrides=types)
                self.assertEqual(scale, records[0].childs[0].value.scale)
                self.assertEqual('<d>%s</d>' % rendered, render_xml(
                    Record.parse(io.BytesIO(dump_records(records)))))
        # no exponent in xsd:decimal: 1E+5000000 is refused, not computed
        for text in ('abc', '1E+5000000', '1e2', ' ', '.', '1.2.3',
                     '79228162514264337593543950336', '0.' + '1' * 29,
                     '9' * 100000):
            with self.subTest(text=text[:20]), self.assertRaises(ValueError):
                XMLParser.parse('<d>%s</d>' % text, type_overrides=types)
        for args in ((False, 1 << 32, 0, 0), (False, 0, 1 << 64, 0),
                     (False, -1, 0, 0), (False, 0, 0, 29)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                Decimal(*args)

    def test_float_out_of_range(self):
        # refused when the XML is read, not made INF nor left to dump_records()
        for kind, text in (('float', '1e39'), ('float', '-3.5e38'),
                           ('double', '1e400'), ('double', '-1e309')):
            with self.subTest(kind=kind, text=text), self.assertRaises(ValueError):
                XMLParser.parse('<f>%s</f>' % text, type_overrides={'/f': kind})
        for kind, text in (('float', '3.40282347E+38'), ('double', 'INF'), ('float', '-INF')):
            with self.subTest(kind=kind, text=text):
                XMLParser.parse('<f>%s</f>' % text, type_overrides={'/f': kind})

    def test_length_prefixed_bounds(self):
        # Chars32Text and Bytes32Text have a signed INT32 length
        self.assertEqual(0x7fffffff, Chars32TextRecord.max_length())
        self.assertEqual(0x7fffffff, Bytes32TextRecord.max_length())


if __name__ == '__main__':
    unittest.main()
