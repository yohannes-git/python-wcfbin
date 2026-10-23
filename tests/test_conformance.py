"""Regression checks based on Microsoft MC-NBFX and issue #15.

These are implementation tests and a few Microsoft byte examples, NOT a
complete WCF/.NET interoperability or MC-NBFSE certification suite.
"""

import io
import re
import unittest
from xml.etree import ElementTree as ET

from wcf.datatypes import MultiByteInt31, Utf8String, Decimal
from wcf.records import (
    ArrayRecord, BoolTextRecord, Chars8TextRecord, Chars16TextRecord,
    Chars32TextRecord, CommentRecord, DatetimeTextRecord, DecimalTextRecord,
    DatetimeTextRecord, DoubleTextRecord, FloatTextRecord, Int16TextRecord, Int32TextRecord,
    Record, ShortAttributeRecord, ShortElementRecord, ShortXmlnsAttributeRecord,
    StartListTextRecord, TimeSpanTextRecord, UnicodeChars8TextRecord,
    dump_records, render_xml,
)
from wcf.xml2records import XMLParser


class TextDefaults(unittest.TestCase):
    def test_version_is_never_auto_typed(self):
        xml = '<r><ClientVersion>8.0</ClientVersion><bool>true</bool><id>42</id></r>'
        root = XMLParser.parse(xml)[0]
        self.assertTrue(all(isinstance(c.childs[0], Chars8TextRecord)
                            for c in root.childs))
        wire = dump_records([root])
        self.assertEqual(xml, render_xml(Record.parse(io.BytesIO(wire))))

    def test_attribute_no_auto_typing(self):
        records = XMLParser.parse('<r ver="8.0" ok="true" num="00012"/>')
        self.assertTrue(all(isinstance(a.value, Chars8TextRecord)
                            for a in records[0].attributes))
        self.assertEqual('8.0', records[0].attributes[0].value.value)
        self.assertEqual('00012', records[0].attributes[2].value.value)

    def test_unicode_text_lengths(self):
        for n, cls in ((127, Chars8TextRecord), (128, Chars16TextRecord),
                       (256, Chars16TextRecord), (66000, Chars32TextRecord)):
            with self.subTest(n=n):
                xml = '<test>' + 'é' * n + '</test>'
                p = XMLParser.parse(xml)
                self.assertIsInstance(p[0].childs[0], cls)
                out = render_xml(Record.parse(io.BytesIO(dump_records(p))))
                self.assertEqual(xml, out)

    def test_mixed_content_preserves_all_whitespace(self):
        xml = '<r> before <a x="a &amp; b"> inside </a> after </r>'
        wire = dump_records(XMLParser.parse(xml))
        self.assertEqual(xml, render_xml(Record.parse(io.BytesIO(wire))))

    def test_xml_entities_and_escaped_attributes(self):
        xml = '<x att="&quot; &amp; &lt;">&amp;&lt;&gt;"</x>'
        wire = dump_records(XMLParser.parse(xml))
        self.assertEqual(xml, render_xml(Record.parse(io.BytesIO(wire))))
        ET.fromstring(render_xml(Record.parse(io.BytesIO(wire))))

    def test_comment_exact_and_mixed_xml(self):
        xml = '<r>a<!--hello-->b</r>'
        self.assertEqual(xml, render_xml(Record.parse(io.BytesIO(
            dump_records(XMLParser.parse(xml))))))

    def test_comment_outside_root(self):
        xml = '<!--before--><r/><!--after-->'
        self.assertEqual('<!--before--><r></r><!--after-->',
                         render_xml(XMLParser.parse(xml)))

    def test_attribute_whitespace_character_references(self):
        xml = '<r a="a&#10;b&#9;c&#13;d"/>'
        back = render_xml(Record.parse(io.BytesIO(dump_records(XMLParser.parse(xml)))))
        self.assertEqual('a\nb\tc\rd', ET.fromstring(back).attrib['a'])

    def test_reject_doctype_and_pi(self):
        with self.assertRaises(ValueError):
            XMLParser.parse('<!DOCTYPE x [<!ENTITY y "z">]><x>&y;</x>')
        with self.assertRaises(ValueError):
            XMLParser.parse('<x><?target value?></x>')

    def test_utf8_names_use_multibyte_lengths(self):
        name = 'x' * 128
        r = XMLParser.parse('<%s />' % name)
        self.assertEqual(name, Record.parse(io.BytesIO(dump_records(r)))[0].name)


class ExplicitTyping(unittest.TestCase):
    def test_type_map_uses_namespaces_not_just_local_names(self):
        xml = ('<r xmlns:a="urn:A" xmlns:b="urn:B">'
               '<a:Version>8.0</a:Version><b:Version>8.0</b:Version></r>')
        overrides = {'/r/{urn:A}Version': 'double'}
        records = XMLParser.parse(xml, type_overrides=overrides)
        self.assertIsInstance(records[0].childs[0].childs[0], DoubleTextRecord)
        self.assertIsInstance(records[0].childs[1].childs[0], Chars8TextRecord)
        self.assertEqual('8.0', records[0].childs[1].childs[0].value)

    def test_explicit_float_and_uint32_boundaries(self):
        xml = '<root><n>-128</n><f>1.5</f></root>'
        result = XMLParser.parse(xml, {'/root/n': 'int8', '/root/f': 'float'})
        self.assertEqual(0x88, result[0].childs[0].childs[0].type)
        self.assertIsInstance(result[0].childs[1].childs[0], FloatTextRecord)

    def test_explicit_attribute(self):
        xml = '<r xmlns:x="urn:x" x:num="-42" num="42"/>'
        result = XMLParser.parse(xml, {'/r/@{urn:x}num': 'int16'})
        attr_by_name = {getattr(a, 'prefix', ''): a for a in result[0].attributes
                        if hasattr(a, 'value') and hasattr(a.value, 'type')}
        self.assertIsInstance(attr_by_name['x'].value, Int16TextRecord)
        self.assertIsInstance(attr_by_name[''].value, Chars8TextRecord)

    def test_raises_on_invalid_type_or_value(self):
        for typ, val in [('bool', 'maybe'), ('uint64', '-1'),
                         ('int8', '128'), ('double', '8.0.1'),
                         ('uuid', 'invalid'), ('unsupported', '1')]:
            with self.subTest(typ=typ, val=val), self.assertRaises(ValueError):
                XMLParser.parse('<x>%s</x>' % val, {'/x': typ})

    def test_explicit_bytes_and_decimal(self):
        records = XMLParser.parse('<r><b>YWJj</b><d>0.00001</d></r>',
                                   {'/r/b': 'bytes', '/r/d': 'decimal'})
        self.assertEqual('YWJj', str(records[0].childs[0].childs[0]))
        self.assertIsInstance(records[0].childs[1].childs[0], DecimalTextRecord)
        self.assertEqual('0.00001', str(records[0].childs[1].childs[0]))


class BinaryFidelity(unittest.TestCase):
    def test_multi_byte_int_31_full_range(self):
        for n in (0, 127, 128, 16383, 16384, (1 << 21) - 1,
                  1 << 21, 0xfffffff, 0x10000000, 0x3fffffff,
                  0x40000000, 0x7fffffff):
            with self.subTest(n=n):
                data = MultiByteInt31(n).to_bytes()
                self.assertEqual(n, MultiByteInt31.parse(io.BytesIO(data)).value)
        self.assertEqual(b'\xff\xff\xff\xff\x07',
                         MultiByteInt31(0x7fffffff).to_bytes())
        for n in (-1, 1 << 31):
            with self.assertRaises(ValueError):
                MultiByteInt31(n).to_bytes()
        for bad in (b'', b'\x80', b'\xff\xff\xff\xff\x08'):
            with self.assertRaises(ValueError):
                MultiByteInt31.parse(io.BytesIO(bad))

    def test_utf8_string_length_uses_multibyte_int(self):
        for text in ('a' * 300, '☀' * 70):
            self.assertEqual(text, Utf8String.parse(io.BytesIO(
                Utf8String(text).to_bytes())).value)
        with self.assertRaises(ValueError):
            Utf8String.parse(io.BytesIO(b'\x82\x01abc'))

    def test_round_trip_explicit_end(self):
        binary = b'@\x01a\x98\x01x\x01'
        records = Record.parse(io.BytesIO(binary))
        self.assertEqual(binary, dump_records(records))
        self.assertEqual(binary, dump_records(records))
        self.assertEqual(0x98, records[0].childs[0].type)
        self.assertEqual('explicit', records[0]._wcf_closure)

    def test_round_trip_implicit_end(self):
        binary = b'@\x01a\x99\x01x'
        records = Record.parse(io.BytesIO(binary))
        self.assertEqual(binary, dump_records(records))
        self.assertEqual(binary, dump_records(records))
        self.assertEqual(0x98, records[0].childs[0].type)
        self.assertEqual('implicit', records[0]._wcf_closure)

    def test_types_preserved_by_inmemory_modify(self):
        binary = b'@\x01x\x8d\x02\x00\x00\x00'
        records = Record.parse(io.BytesIO(binary))
        self.assertIsInstance(records[0].childs[0], Int32TextRecord)
        records[0].childs[0].value = 8
        encoded = dump_records(records)
        self.assertEqual(0x8d, encoded[3])
        self.assertEqual('8', str(Record.parse(io.BytesIO(encoded))[0].childs[0]))

    def test_byte_identical_real_example(self):
        from pathlib import Path
        binary = (Path(__file__).parent.parent / 'example.bin').read_bytes()
        self.assertEqual(binary, dump_records(Record.parse(io.BytesIO(binary))))

    def test_array_namespace_and_attributes(self):
        # Microsoft MC-NBFX section 2.3.3: <item xmlns="http://tempuri.org">1 ...
        elem = ShortElementRecord('item')
        attrs = [ShortXmlnsAttributeRecord('http://tempuri.org'),
                 ShortAttributeRecord('v', Chars8TextRecord('ok'))]
        a = ArrayRecord(elem, [Int32TextRecord(1), Int32TextRecord(2),
                               Int32TextRecord(3)], attrs)
        encoded = a.to_bytes()
        decoded = Record.parse(io.BytesIO(encoded))
        self.assertEqual(encoded, dump_records(decoded))
        xml = render_xml(decoded)
        self.assertEqual(3, xml.count('xmlns="http://tempuri.org"'))
        self.assertEqual(3, xml.count('v="ok"'))
        ET.fromstring('<r>' + xml + '</r>')

    def test_array_with_prefix_xml(self):
        from wcf.records import ElementRecord, XmlnsAttributeRecord
        elem = ElementRecord('long', 'item')
        a = ArrayRecord(elem, [Int16TextRecord(10), Int16TextRecord(12)],
                        [XmlnsAttributeRecord('long', 'urn:long')])
        self.assertEqual('<long:item xmlns:long="urn:long">10</long:item>'
                         '<long:item xmlns:long="urn:long">12</long:item>',
                         render_xml(Record.parse(io.BytesIO(a.to_bytes()))))

    def test_list_records_can_be_in_attributes(self):
        binary = (b'@\x01x\x04\x01a\xa4\x88\x7b\x98\x05hello'
                  b'\x86\xa6\x01')
        records = Record.parse(io.BytesIO(binary))
        self.assertIsInstance(records[0].attributes[0].value, StartListTextRecord)
        self.assertEqual(binary, dump_records(records))
        self.assertEqual('<x a="123 hello true"></x>', render_xml(records))

    def test_reserved_records_raise(self):
        for rec in (0, 0x7a, 0xa5, 0xa7, 0xbe, 0xff):
            with self.subTest(rec=rec), self.assertRaises(ValueError):
                Record.parse(io.BytesIO(bytes((rec,))))

    def test_non_canonical_multibyte_lengths_rejected(self):
        # MC-NBFX 2.1.2 maps each integer range to exactly one packet size.
        for raw in (b'\x80\x00', b'\x81\x00',
                    b'\x80\x80\x00', b'\x80\x80\x80\x00',
                    b'\x80\x80\x80\x80\x00'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                MultiByteInt31.parse(io.BytesIO(raw))

    def test_datetime_rejects_invalid_encoder_bits(self):
        for ticks, tz in ((0, 3), (-1, 0), (3155378976000000000, 1)):
            with self.subTest(ticks=ticks, tz=tz), self.assertRaises(ValueError):
                DatetimeTextRecord(ticks, tz).to_bytes()

    def test_endlist_only_allowed_inside_startlist(self):
        with self.assertRaisesRegex(ValueError, 'EndListText'):
            Record.parse(io.BytesIO(b'\x40\x01x\xa6\x01'))

    def test_bool_and_empty_text(self):
        self.assertEqual('<a>true</a>', render_xml(Record.parse(io.BytesIO(
            b'@\x01a\xb5\x01'))))
        self.assertEqual('<a></a>', render_xml(Record.parse(io.BytesIO(
            b'@\x01a\xa9'))))
        with self.assertRaises(ValueError):
            BoolTextRecord.parse(io.BytesIO(b'\x02'))

    def test_time_span_ticks_from_microsoft_spec(self):
        # MC-NBFX section 3 examples
        self.assertEqual('<doc>-PT5M44S</doc>', render_xml(Record.parse(io.BytesIO(
            bytes.fromhex('40 03 64 6F 63 AE 00 C4 F5 32 FF FF FF FF 01')))))
        self.assertEqual('<a>PT3H20M</a>', render_xml(Record.parse(io.BytesIO(
            bytes.fromhex('40 01 61 AF 00 B0 8E F0 1B 00 00 00')))))
        # XmlConvert.ToString(TimeSpan)
        self.assertEqual('PT1S', str(TimeSpanTextRecord(10000000)))
        self.assertEqual('-PT1.0000001S', str(TimeSpanTextRecord(-10000001)))
        self.assertEqual('P1DT2H3M4.5S', str(TimeSpanTextRecord(
            ((86400 + 2 * 3600 + 3 * 60 + 4) * 10000000) + 5000000)))
        self.assertEqual('P2D', str(TimeSpanTextRecord(2 * 864000000000)))
        self.assertEqual('PT0.0000001S', str(TimeSpanTextRecord(1)))
        self.assertEqual('-P10675199DT2H48M5.4775808S',
                         str(TimeSpanTextRecord(-(1 << 63))))

    def test_datetime_local_at_the_ends_of_the_range(self):
        # DateTime.MinValue and MaxValue with Kind=Local
        for ticks, date in ((0, '0001-01-01T00:00:00'), (3155378975999999999,
                                                '9999-12-31T23:59:59.9999999')):
            with self.subTest(ticks=ticks):
                self.assertRegex(str(DatetimeTextRecord(ticks, 2)),
                                 '^' + re.escape(date) + r'[+-]\d\d:\d\d$')

    def test_datetime_preserves_100_ns_and_utc(self):
        self.assertEqual('0001-01-01T00:00:00.0000001',
                         str(DatetimeTextRecord(1, 0)))
        self.assertEqual('1970-01-01T00:00:00.0000001Z',
                         str(DatetimeTextRecord(621355968000000001, 1)))

    def test_datetime_local_uses_offset(self):
        self.assertRegex(str(DatetimeTextRecord(621355968000000001, 2)),
                         r'^1970-01-01T00:00:00\.0000001[+-][0-9]{2}:[0-9]{2}$')

    def test_decimal_less_than_one(self):
        self.assertEqual('0.001', str(Decimal(False, 0, 1, 3)))
        self.assertEqual('-0.01', str(Decimal(True, 0, 1, 2)))
        self.assertEqual('1.23', str(Decimal(False, 0, 12300, 4)))

    def test_nan_lexical_casing(self):
        self.assertEqual('NaN', str(DoubleTextRecord(float('nan'))))
        self.assertEqual('NaN', str(FloatTextRecord(float('nan'))))


if __name__ == '__main__':
    unittest.main()
