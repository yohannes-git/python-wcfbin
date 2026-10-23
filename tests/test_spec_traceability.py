"""Traceability tests: [MC-NBFX], [MC-NBFS] and [MC-NBFSE], requirement by
requirement.

Every test method is named after the identifier of the requirement it
proves in CONFORMANCE.md ("NBFX-2.2.3.15-LEN-POSITIVE" is
test_NBFX_2_2_3_15_LEN_POSITIVE). One TestCase per section of the
specifications.

The tests decorated with @nonconformant prove a requirement that the
current code does NOT meet: they fail until the code (or the decision
recorded in README.md) changes. Set WCF_TRACE_EXPECT_NONCONFORMANT=1 to
run them as expected failures.

Run from the top of the repository:

    python3 -m unittest tests.test_spec_traceability
"""

import contextlib
import hashlib
import io
import os
import struct
import unittest
from unittest import mock

import wcf.dictionary
from wcf.datatypes import Decimal, MultiByteInt31, Utf8String
from wcf.dictionary import dictionary_context, static_dictionary
from wcf.errors import WcfBinaryError
from wcf.records import (
    ArrayRecord, Attribute, AttributeRecord, BoolTextRecord, Bytes8TextRecord,
    Bytes16TextRecord, Bytes32TextRecord, Chars8TextRecord, Chars16TextRecord,
    Chars32TextRecord, CommentRecord, DatetimeTextRecord, DecimalTextRecord,
    DictionaryAttributeRecord, DictionaryElementRecord, DictionaryTextRecord,
    DictionaryXmlnsAttributeRecord, DoubleTextRecord, Element, ElementRecord,
    EmptyTextRecord, EndElementRecord, EndListTextRecord, FalseTextRecord,
    FloatTextRecord, Int8TextRecord, Int16TextRecord, Int32TextRecord,
    Int64TextRecord, OneTextRecord, QNameDictionaryTextRecord, Record,
    ShortAttributeRecord, ShortDictionaryAttributeRecord,
    ShortDictionaryElementRecord, ShortDictionaryXmlnsAttributeRecord,
    ShortElementRecord, ShortXmlnsAttributeRecord, StartListTextRecord, Text,
    TimeSpanTextRecord, TrueTextRecord, UInt64TextRecord,
    UnicodeChars8TextRecord, UnicodeChars16TextRecord,
    UnicodeChars32TextRecord, UniqueIdTextRecord, UuidTextRecord,
    XmlnsAttributeRecord, ZeroTextRecord, dump_records, render_xml)
from wcf.records.attributes import PREFIX_ATTRIBUTES, PREFIX_DICTIONARY_ATTRIBUTES
from wcf.records.elements import PREFIX_DICTIONARY_ELEMENTS, PREFIX_ELEMENTS
from wcf.session import BinaryXmlSession, encode_string_table
from wcf.xml2records import XMLParser

_EXPECT_NC = os.environ.get('WCF_TRACE_EXPECT_NONCONFORMANT') == '1'


def nonconformant(reason):
    """Mark a test proving a requirement that the current code does not
    meet (it fails; an expected failure with
    WCF_TRACE_EXPECT_NONCONFORMANT=1)."""
    def mark(test):
        test.__doc__ = 'NON-CONFORMANT, fails on the current code: ' + reason
        test.nonconformant = True
        return unittest.expectedFailure(test) if _EXPECT_NC else test
    return mark


def h(text):
    return bytes.fromhex(text)


def decode(data):
    return Record.parse(io.BytesIO(data))


def render(data):
    return render_xml(decode(data))


def mbi31(data):
    return MultiByteInt31.parse(io.BytesIO(data)).value


class _StrN(dict):
    """MC-NBFX section 3: "Records that refer to strings outside the
    document are shown as "strXXX" where XXX is the integer value"."""

    def __contains__(self, key):
        return isinstance(key, int) and key >= 0

    def __getitem__(self, key):
        return 'str%d' % key


@contextlib.contextmanager
def strn_dictionary():
    with mock.patch.object(wcf.dictionary.dictionary, '_static', _StrN()):
        yield


def record_types(records):
    """The record types a decoded tree is made of, *WithEndElement and
    EndElement as they were on the wire."""
    found = set()

    def text(record):
        found.add(record.type)
        if isinstance(record, StartListTextRecord):
            found.add(EndListTextRecord.type)
            for item in record.values:
                text(item)

    def attribute(record):
        found.add(record.type)
        if not record.is_xmlns:
            text(record.value)

    def walk(siblings):
        for record in siblings:
            if isinstance(record, ArrayRecord):
                found.update((0x03, record.element.type, 0x01, record.recordtype))
                for a in record.attributes:
                    attribute(a)
            elif isinstance(record, Element):
                found.add(record.type)
                for a in record.attributes:
                    attribute(a)
                walk(record.childs)
                if record._wcf_closure == 'implicit':
                    found.add(record.childs[-1].type + 1)
                else:
                    found.add(0x01)
            elif isinstance(record, Text):
                text(record)
            else:
                found.add(record.type)
    walk(records)
    return found


# MC-NBFX 2.1.1, Table 1 (names as in the specification)
RECORD_NAMES = {0x00: None, 0x01: 'EndElement', 0x02: 'Comment', 0x03: 'Array',
                0x04: 'ShortAttribute', 0x05: 'Attribute',
                0x06: 'ShortDictionaryAttribute', 0x07: 'DictionaryAttribute',
                0x08: 'ShortXmlnsAttribute', 0x09: 'XmlnsAttribute',
                0x0A: 'ShortDictionaryXmlnsAttribute',
                0x0B: 'DictionaryXmlnsAttribute',
                0x40: 'ShortElement', 0x41: 'Element',
                0x42: 'ShortDictionaryElement', 0x43: 'DictionaryElement'}
for _i, _letter in enumerate('ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
    RECORD_NAMES[0x0C + _i] = 'PrefixDictionaryAttribute' + _letter
    RECORD_NAMES[0x26 + _i] = 'PrefixAttribute' + _letter
    RECORD_NAMES[0x44 + _i] = 'PrefixDictionaryElement' + _letter
    RECORD_NAMES[0x5E + _i] = 'PrefixElement' + _letter
_TEXTS = ['ZeroText', 'OneText', 'FalseText', 'TrueText', 'Int8Text',
          'Int16Text', 'Int32Text', 'Int64Text', 'FloatText', 'DoubleText',
          'DecimalText', 'DateTimeText', 'Chars8Text', 'Chars16Text',
          'Chars32Text', 'Bytes8Text', 'Bytes16Text', 'Bytes32Text',
          'StartListText', 'EndListText', 'EmptyText',
          'DictionaryText', 'UniqueIdText', 'TimeSpanText', 'UuidText',
          'UInt64Text', 'BoolText', 'UnicodeChars8Text', 'UnicodeChars16Text',
          'UnicodeChars32Text', 'QNameDictionaryText']
for _i, _name in enumerate(_TEXTS):
    RECORD_NAMES[0x80 + 2 * _i] = _name
    RECORD_NAMES[0x81 + 2 * _i] = (_name + 'WithEndElement'
                                   if _name and _name not in ('StartListText', 'EndListText')
                                   else None)
for _t in range(0x100):
    RECORD_NAMES.setdefault(_t, None)   # Reserved
RESERVED = sorted(t for t, n in RECORD_NAMES.items() if n is None)

# the class implementing each record name (DateTimeText is DatetimeTextRecord)
CLASS_NAMES = {'DateTimeText': 'DatetimeTextRecord'}

# a payload and the characters it represents, for every text record
TEXT_SAMPLES = {
    0x80: (b'', '0'), 0x82: (b'', '1'), 0x84: (b'', 'false'), 0x86: (b'', 'true'),
    0x88: (b'\x80', '-128'), 0x8A: (b'\x00\x80', '-32768'),
    0x8C: (b'\x00\x00\x00\x80', '-2147483648'),
    0x8E: (b'\x00' * 7 + b'\x80', '-9223372036854775808'),
    0x90: (h('CD CC 8C 3F'), '1.1'),
    0x92: (h('74 57 14 8B 0A BF 05 40'), '2.71828182845905'),
    0x94: (h('00 00 06 00 00 00 00 00 80 2D 4E 00 00 00 00 00'), '5.123456'),
    0x96: (h('FF 3F 37 F4 75 28 CA 2B'), '9999-12-31T23:59:59.9999999'),
    0x98: (b'\x03abc', 'abc'), 0x9A: (b'\x03\x00abc', 'abc'),
    0x9C: (b'\x03\x00\x00\x00abc', 'abc'),
    0x9E: (b'\x03\x01\x02\x03', 'AQID'), 0xA0: (b'\x01\x00\xff', '/w=='),
    0xA2: (b'\x03\x00\x00\x00\x01\x02\x03', 'AQID'),
    0xA4: (h('86 84 80 82 A6'), 'true false 0 1'),
    0xA8: (b'', ''), 0xAA: (b'\x02', 'Envelope'),
    0xAC: (h('00 11 22 33 44 55 66 77 88 99 AA BB CC DD EE FF'),
           'urn:uuid:33221100-5544-7766-8899-aabbccddeeff'),
    0xAE: (h('00 C4 F5 32 FF FF FF FF'), '-PT5M44S'),
    0xB0: (h('00 11 22 33 44 55 66 77 88 99 AA BB CC DD EE FF'),
           '33221100-5544-7766-8899-aabbccddeeff'),
    0xB2: (b'\xff' * 8, '18446744073709551615'), 0xB4: (b'\x01', 'true'),
    0xB6: (b'\x06a\x00b\x00c\x00', 'abc'), 0xB8: (b'\x06\x00a\x00b\x00c\x00', 'abc'),
    0xBA: (b'\x06\x00\x00\x00a\x00b\x00c\x00', 'abc'),
    0xBC: (b'\x01\x02', 'b:Envelope'),
}

# MC-NBFX section 3, every row: (record, type, bytes, characters represented).
# The line breaks of the published table are removed ("there is no carriage
# return or line feed included here"); in the PrefixAttributeK row the
# published table has two spaces before "k:attr", a layout artefact: one
# space separates attributes (2.2.2.10).
SECTION3 = [
    ('EndElement', 0x01, '40 03 64 6F 63 01',
     '<doc></doc>'),
    ('Comment', 0x02, '02 07 63 6F 6D 6D 65 6E 74',
     '<!--comment-->'),
    ('Array', 0x03, '03 40 03 61 72 72 01 8B 03 33 33 88 88 DD DD',
     '<arr>13107</arr><arr>-30584</arr><arr>-8739</arr>'),
    ('ShortAttribute', 0x04, '40 03 64 6F 63 04 04 61 74 74 72 84 01',
     '<doc attr="false"></doc>'),
    ('Attribute', 0x05, '40 03 64 6F 63 09 03 70 72 65 0A 68 74 74 70 3A 2F 2F 61 62 63 05 03 70 72 65 04 61 74 74 72 84 01',
     '<doc xmlns:pre="http://abc" pre:attr="false"></doc>'),
    ('ShortDictionaryAttribute', 0x06, '40 03 64 6F 63 06 08 86 01',
     '<doc str8="true"></doc>'),
    ('DictionaryAttribute', 0x07, '40 03 64 6F 63 09 03 70 72 65 0A 68 74 74 70 3A 2F 2F 61 62 63 07 03 70 72 65 00 86 01',
     '<doc xmlns:pre="http://abc" pre:str0="true"></doc>'),
    ('ShortXmlnsAttribute', 0x08, '40 03 64 6F 63 08 0A 68 74 74 70 3A 2F 2F 61 62 63 01',
     '<doc xmlns="http://abc"></doc>'),
    ('XmlnsAttribute', 0x09, '40 03 64 6F 63 09 01 70 0A 68 74 74 70 3A 2F 2F 61 62 63 01',
     '<doc xmlns:p="http://abc"></doc>'),
    ('ShortDictionaryXmlnsAttribute', 0x0A, '40 03 64 6F 63 0A 04 01',
     '<doc xmlns="str4"></doc>'),
    ('DictionaryXmlnsAttribute', 0x0B, '40 03 64 6F 63 0B 01 70 04 01',
     '<doc xmlns:p="str4"></doc>'),
    ('PrefixDictionaryAttributeF', 0x11, '40 03 64 6F 63 09 01 66 0A 68 74 74 70 3A 2F 2F 61 62 63 11 0B 98 05 68 65 6C 6C 6F 01',
     '<doc xmlns:f="http://abc" f:str11="hello"></doc>'),
    ('PrefixDictionaryAttributeX', 0x23, '40 03 64 6F 63 09 01 78 0A 68 74 74 70 3A 2F 2F 61 62 63 23 15 98 05 77 6F 72 6C 64 01',
     '<doc xmlns:x="http://abc" x:str21="world"></doc>'),
    ('PrefixAttributeK', 0x30, '40 03 64 6F 63 09 01 6B 0A 68 74 74 70 3A 2F 2F 61 62 63 30 04 61 74 74 72 86 01',
     '<doc xmlns:k="http://abc" k:attr="true"></doc>'),
    ('PrefixAttributeZ', 0x3F, '40 03 64 6F 63 09 01 7A 0A 68 74 74 70 3A 2F 2F 61 62 63 3F 03 61 62 63 98 03 78 79 7A 01',
     '<doc xmlns:z="http://abc" z:abc="xyz"></doc>'),
    ('ShortElement', 0x40, '40 03 64 6F 63 01',
     '<doc></doc>'),
    ('Element', 0x41, '41 03 70 72 65 03 64 6F 63 09 03 70 72 65 0A 68 74 74 70 3A 2F 2F 61 62 63 01',
     '<pre:doc xmlns:pre="http://abc"></pre:doc>'),
    ('ShortDictionaryElement', 0x42, '42 0E 01',
     '<str14></str14>'),
    ('DictionaryElement', 0x43, '43 03 70 72 65 0E 09 03 70 72 65 0A 68 74 74 70 3A 2F 2F 61 62 63 01',
     '<pre:str14 xmlns:pre="http://abc"></pre:str14>'),
    ('PrefixDictionaryElementA', 0x44, '44 0A 09 01 61 0A 68 74 74 70 3A 2F 2F 61 62 63 01',
     '<a:str10 xmlns:a="http://abc"></a:str10>'),
    ('PrefixDictionaryElementS', 0x56, '56 26 09 01 73 0A 68 74 74 70 3A 2F 2F 61 62 63 01',
     '<s:str38 xmlns:s="http://abc"></s:str38>'),
    ('PrefixElementA', 0x5E, '5E 05 68 65 6C 6C 6F 09 01 61 0A 68 74 74 70 3A 2F 2F 61 62 63 01',
     '<a:hello xmlns:a="http://abc"></a:hello>'),
    ('PrefixElementS', 0x70, '70 09 4D 79 4D 65 73 73 61 67 65 09 01 73 0A 68 74 74 70 3A 2F 2F 61 62 63 01',
     '<s:MyMessage xmlns:s="http://abc"></s:MyMessage>'),
    ('ZeroText', 0x80, '40 03 64 6F 63 06 A0 03 80 01',
     '<doc str416="0"></doc>'),
    ('ZeroTextWithEndElement', 0x81, '40 03 61 62 63 81',
     '<abc>0</abc>'),
    ('OneText', 0x82, '40 03 64 6F 63 06 00 82 01',
     '<doc str0="1"></doc>'),
    ('OneTextWithEndElement', 0x83, '40 03 61 62 63 83',
     '<abc>1</abc>'),
    ('FalseText', 0x84, '40 03 64 6F 63 06 00 84 01',
     '<doc str0="false"></doc>'),
    ('FalseTextWithEndElement', 0x85, '40 03 61 62 63 85',
     '<abc>false</abc>'),
    ('TrueText', 0x86, '40 03 64 6F 63 06 00 86 01',
     '<doc str0="true"></doc>'),
    ('TrueTextWithEndElement', 0x87, '40 03 61 62 63 87',
     '<abc>true</abc>'),
    ('Int8Text', 0x88, '40 03 64 6F 63 06 EC 01 88 DE 01',
     '<doc str236="-34"></doc>'),
    ('Int8TextWithEndElement', 0x89, '42 9A 01 89 7F',
     '<str154>127</str154>'),
    ('Int16Text', 0x8A, '40 03 64 6F 63 06 EC 01 8A 00 80 01',
     '<doc str236="-32768"></doc>'),
    ('Int16TextWithEndElement', 0x8B, '42 9A 01 8B FF 7F',
     '<str154>32767</str154>'),
    ('Int32Text', 0x8C, '40 03 64 6F 63 06 EC 01 8C 15 CD 5B 07 01',
     '<doc str236="123456789"></doc>'),
    ('Int32TextWithEndElement', 0x8D, '42 9A 01 8D FF FF FF 7F',
     '<str154>2147483647</str154>'),
    ('Int64Text', 0x8E, '40 03 64 6F 63 06 EC 01 8E 00 00 00 80 00 00 00 00 01',
     '<doc str236="2147483648"></doc>'),
    ('Int64TextWithEndElement', 0x8F, '42 9A 01 8F 00 00 00 00 00 01 00 00',
     '<str154>1099511627776</str154>'),
    ('FloatText', 0x90, '40 03 64 6F 63 04 01 61 90 CD CC 8C 3F 01',
     '<doc a="1.1"></doc>'),
    ('FloatTextWithEndElement', 0x91, '40 05 50 72 69 63 65 91 CD CC 01 42',
     '<Price>32.45</Price>'),
    ('DoubleText', 0x92, '40 03 64 6F 63 04 01 61 92 74 57 14 8B 0A BF 05 40 01',
     '<doc a="2.71828182845905"></doc>'),
    ('DoubleTextWithEndElement', 0x93, '40 02 50 49 93 11 2D 44 54 FB 21 09 40',
     '<PI>3.14159265358979</PI>'),
    ('DecimalText', 0x94, '40 03 64 6F 63 04 03 69 6E 74 94 00 00 06 00 00 00 00 00 80 2D 4E 00 00 00 00 00 01',
     '<doc int="5.123456"></doc>'),
    ('DecimalTextWithEndElement', 0x95, '40 08 4D 61 78 56 61 6C 75 65 95 00 00 00 00 FF FF FF FF FF FF FF FF FF FF FF FF',
     '<MaxValue>79228162514264337593543950335</MaxValue>'),
    ('DateTimeText', 0x96, '40 03 64 6F 63 06 6E 96 FF 3F 37 F4 75 28 CA 2B 01',
     '<doc str110="9999-12-31T23:59:59.9999999"></doc>'),
    ('DateTimeTextWithEndElement', 0x97, '42 6C 97 00 40 8E F9 5B 47 C8 08',
     '<str108>2006-05-17T00:00:00</str108>'),
    ('Chars8Text', 0x98, '40 03 64 6F 63 98 05 68 65 6C 6C 6F 01',
     '<doc>hello</doc>'),
    ('Chars8TextWithEndElement', 0x99, '40 01 61 99 05 68 65 6C 6C 6F',
     '<a>hello</a>'),
    ('Chars16Text', 0x9A, '40 03 64 6F 63 9A 05 00 68 65 6C 6C 6F 01',
     '<doc>hello</doc>'),
    ('Chars16TextWithEndElement', 0x9B, '40 01 61 9B 05 00 68 65 6C 6C 6F',
     '<a>hello</a>'),
    ('Chars32Text', 0x9C, '40 03 64 6F 63 9C 05 00 00 00 68 65 6C 6C 6F 01',
     '<doc>hello</doc>'),
    ('Chars32TextWithEndElement', 0x9D, '40 01 61 9D 05 00 00 00 68 65 6C 6C 6F',
     '<a>hello</a>'),
    ('Bytes8Text', 0x9E, '40 03 64 6F 63 9E 08 00 01 02 03 04 05 06 07 01',
     '<doc>AAECAwQFBgc=</doc>'),
    ('Bytes8TextWithEndElement', 0x9F, '40 06 42 61 73 65 36 34 9F 08 00 01 02 03 04 05 06 07',
     '<Base64>AAECAwQFBgc=</Base64>'),
    ('Bytes16Text', 0xA0, '40 03 64 6F 63 A0 08 00 00 01 02 03 04 05 06 07 01',
     '<doc>AAECAwQFBgc=</doc>'),
    ('Bytes16TextWithEndElement', 0xA1, '40 06 42 61 73 65 36 34 A1 08 00 00 01 02 03 04 05 06 07',
     '<Base64>AAECAwQFBgc=</Base64>'),
    ('Bytes32Text', 0xA2, '40 03 64 6F 63 A2 08 00 00 00 00 01 02 03 04 05 06 07 01',
     '<doc>AAECAwQFBgc=</doc>'),
    ('Bytes32TextWithEndElement', 0xA3, '40 06 42 61 73 65 36 34 A3 08 00 00 00 00 01 02 03 04 05 06 07',
     '<Base64>AAECAwQFBgc=</Base64>'),
    ('StartListText', 0xA4, '40 03 64 6F 63 04 01 61 A4 88 7B 98 05 68 65 6C 6C 6F 86 A6 01',
     '<doc a="123 hello true"></doc>'),
    ('EndListText', 0xA6, '40 03 64 6F 63 04 01 61 A4 88 7B 98 05 68 65 6C 6C 6F 86 A6 01',
     '<doc a="123 hello true"></doc>'),
    ('EmptyText', 0xA8, '40 03 64 6F 63 04 01 61 A8 01',
     '<doc a=""></doc>'),
    ('EmptyTextWithEndElement', 0xA9, '40 03 64 6F 63 A9',
     '<doc></doc>'),
    ('DictionaryText', 0xAA, '40 03 64 6F 63 04 02 6E 73 AA 38 01',
     '<doc ns="str56"></doc>'),
    ('DictionaryTextWithEndElement', 0xAB, '40 04 54 79 70 65 AB C4 01',
     '<Type>str196</Type>'),
    ('UniqueIdText', 0xAC, '40 03 64 6F 63 AC 00 11 22 33 44 55 66 77 88 99 AA BB CC DD EE FF 01',
     '<doc>urn:uuid:33221100-5544-7766-8899-aabbccddeeff</doc>'),
    ('UniqueIdTextWithEndElement', 0xAD, '42 1A AD 00 11 22 33 44 55 66 77 88 99 AA BB CC DD EE FF',
     '<str26>urn:uuid:33221100-5544-7766-8899-aabbccddeeff</str26>'),
    ('TimeSpanText', 0xAE, '40 03 64 6F 63 AE 00 C4 F5 32 FF FF FF FF 01',
     '<doc>-PT5M44S</doc>'),
    ('TimeSpanTextWithEndElement', 0xAF, '42 94 07 AF 00 B0 8E F0 1B 00 00 00',
     '<str916>PT3H20M</str916>'),
    ('UuidText', 0xB0, '40 03 64 6F 63 B0 00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F 01',
     '<doc>03020100-0504-0706-0809-0a0b0c0d0e0f</doc>'),
    ('UuidTextWithEndElement', 0xB1, '40 02 49 44 B1 00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F',
     '<ID>03020100-0504-0706-0809-0a0b0c0d0e0f</ID>'),
    ('UInt64Text', 0xB2, '40 03 64 6F 63 B2 FF FF FF FF FF FF FF FF 01',
     '<doc>18446744073709551615</doc>'),
    ('UInt64TextWithEndElement', 0xB3, '42 9A 01 B3 FE FF FF FF FF FF FF FF',
     '<str154>18446744073709551614</str154>'),
    ('BoolText', 0xB4, '40 03 64 6F 63 B4 01 01',
     '<doc>true</doc>'),
    ('BoolTextWithEndElement', 0xB5, '03 40 03 61 72 72 01 B5 05 01 00 01 00 01',
     '<arr>true</arr><arr>false</arr><arr>true</arr><arr>false</arr><arr>true</arr>'),
    ('UnicodeChars8Text', 0xB6, '40 03 64 6F 63 04 01 75 B6 06 75 00 6E 00 69 00 01',
     '<doc u="uni"></doc>'),
    ('UnicodeChars8TextWithEndElement', 0xB7, '40 01 55 B7 06 75 00 6E 00 69 00',
     '<U>uni</U>'),
    ('UnicodeChars16Text', 0xB8, '40 03 64 6F 63 04 03 75 31 36 B8 08 00 75 00 6E 00 69 00 32 00 01',
     '<doc u16="uni2"></doc>'),
    ('UnicodeChars16TextWithEndElement', 0xB9, '40 03 55 31 36 B9 08 00 75 00 6E 00 69 00 32 00',
     '<U16>uni2</U16>'),
    ('UnicodeChars32Text', 0xBA, '40 03 64 6F 63 04 03 75 33 32 BA 04 00 00 00 33 00 32 00 01',
     '<doc u32="32"></doc>'),
    ('UnicodeChars32TextWithEndElement', 0xBB, '40 03 55 33 32 BB 04 00 00 00 33 00 32 00',
     '<U32>32</U32>'),
    ('QNameDictionaryText', 0xBC, '40 03 64 6F 63 06 F0 06 BC 08 8E 07 01',
     '<doc str880="i:str910"></doc>'),
    ('QNameDictionaryTextWithEndElement', 0xBD, '40 04 54 79 70 65 BD 12 90 07',
     '<Type>s:str912</Type>'),
]


def S(text):
    """A MC-NBFX String (2.1.3)."""
    return Utf8String(text).to_bytes()


_UUID = '33221100-5544-7766-8899-aabbccddeeff'
TEXT_FACTORIES = {
    0x80: ZeroTextRecord, 0x82: OneTextRecord, 0x84: FalseTextRecord,
    0x86: TrueTextRecord,
    0x88: lambda: Int8TextRecord(-128), 0x8A: lambda: Int16TextRecord(-32768),
    0x8C: lambda: Int32TextRecord(-2 ** 31), 0x8E: lambda: Int64TextRecord(-2 ** 63),
    0x90: lambda: FloatTextRecord(struct.unpack('<f', h('CD CC 8C 3F'))[0]),
    0x92: lambda: DoubleTextRecord(struct.unpack('<d', h('74 57 14 8B 0A BF 05 40'))[0]),
    0x94: lambda: DecimalTextRecord(Decimal(False, 0, 5123456, 6)),
    0x96: lambda: DatetimeTextRecord(3155378975999999999, 0),
    0x98: lambda: Chars8TextRecord('abc'), 0x9A: lambda: Chars16TextRecord('abc'),
    0x9C: lambda: Chars32TextRecord('abc'),
    0x9E: lambda: Bytes8TextRecord(b'\x01\x02\x03'),
    0xA0: lambda: Bytes16TextRecord(b'\xff'),
    0xA2: lambda: Bytes32TextRecord(b'\x01\x02\x03'),
    0xA4: lambda: StartListTextRecord([TrueTextRecord(), FalseTextRecord(),
                                       ZeroTextRecord(), OneTextRecord()]),
    0xA8: EmptyTextRecord, 0xAA: lambda: DictionaryTextRecord(2),
    0xAC: lambda: UniqueIdTextRecord('urn:uuid:' + _UUID),
    0xAE: lambda: TimeSpanTextRecord(-3440000000),
    0xB0: lambda: UuidTextRecord(_UUID), 0xB2: lambda: UInt64TextRecord(2 ** 64 - 1),
    0xB4: lambda: BoolTextRecord(True),
    0xB6: lambda: UnicodeChars8TextRecord('abc'),
    0xB8: lambda: UnicodeChars16TextRecord('abc'),
    0xBA: lambda: UnicodeChars32TextRecord('abc'),
    0xBC: lambda: QNameDictionaryTextRecord('b', 2),
}

# attribute records: (bytes after the record type, attribute as rendered, factory)
ATTRIBUTE_SAMPLES = {
    0x04: (b'\x01a\x86', 'a="true"', lambda: ShortAttributeRecord('a', TrueTextRecord())),
    0x05: (b'\x01p\x01a\x86', 'p:a="true"', lambda: AttributeRecord('p', 'a', TrueTextRecord())),
    0x06: (b'\x02\x86', 'Envelope="true"',
           lambda: ShortDictionaryAttributeRecord(2, TrueTextRecord())),
    0x07: (b'\x01p\x02\x86', 'p:Envelope="true"',
           lambda: DictionaryAttributeRecord('p', 2, TrueTextRecord())),
    0x08: (S('urn:x'), 'xmlns="urn:x"', lambda: ShortXmlnsAttributeRecord('urn:x')),
    0x09: (b'\x01p' + S('urn:x'), 'xmlns:p="urn:x"', lambda: XmlnsAttributeRecord('p', 'urn:x')),
    0x0A: (b'\x06', 'xmlns="http://www.w3.org/2005/08/addressing"',
           lambda: ShortDictionaryXmlnsAttributeRecord(6)),
    0x0B: (b'\x01p\x06', 'xmlns:p="http://www.w3.org/2005/08/addressing"',
           lambda: DictionaryXmlnsAttributeRecord('p', 6)),
}
ELEMENT_SAMPLES = {
    0x40: (b'\x01e', 'e', lambda: ShortElementRecord('e')),
    0x41: (b'\x01p\x01e', 'p:e', lambda: ElementRecord('p', 'e')),
    0x42: (b'\x02', 'Envelope', lambda: ShortDictionaryElementRecord(2)),
    0x43: (b'\x01p\x02', 'p:Envelope', lambda: DictionaryElementRecord('p', 2)),
}
for _i, _letter in enumerate('abcdefghijklmnopqrstuvwxyz'):
    ATTRIBUTE_SAMPLES[0x0C + _i] = (
        b'\x02\x86', '%s:Envelope="true"' % _letter,
        lambda c=PREFIX_DICTIONARY_ATTRIBUTES[_letter]: c(2, TrueTextRecord()))
    ATTRIBUTE_SAMPLES[0x26 + _i] = (
        b'\x01a\x86', '%s:a="true"' % _letter,
        lambda c=PREFIX_ATTRIBUTES[_letter]: c('a', TrueTextRecord()))
    ELEMENT_SAMPLES[0x44 + _i] = (
        b'\x02', '%s:Envelope' % _letter,
        lambda c=PREFIX_DICTIONARY_ELEMENTS[_letter]: c(2))
    ELEMENT_SAMPLES[0x5E + _i] = (
        b'\x01e', '%s:e' % _letter, lambda c=PREFIX_ELEMENTS[_letter]: c('e'))


def _class_name(name):
    return CLASS_NAMES.get(name, name + 'Record')


# ---------------------------------------------------------------- MC-NBFX 1.5

class NBFX_1_5_Applicability(unittest.TestCase):
    """The constructs the format does not represent: the XML input is
    mapped to the supported form, the XML output never uses the others."""

    def test_NBFX_1_5_EMPTY_ELEMENT(self):
        self.assertEqual('<x></x>', render_xml(XMLParser.parse('<x/>')))
        self.assertEqual('<x></x>', render(b'\x40\x01x\x01'))

    def test_NBFX_1_5_CDATA(self):
        records = XMLParser.parse('<x><![CDATA[a<b]]></x>')
        self.assertEqual('a<b', str(records[0].childs[0]))
        self.assertEqual('<x>a&lt;b</x>', render_xml(records))

    def test_NBFX_1_5_CHARREF(self):
        records = XMLParser.parse('<x y="&#65;">&#66;&amp;</x>')
        self.assertEqual('A', str(records[0].attributes[0].value))
        self.assertEqual('B&', str(records[0].childs[0]))

    def test_NBFX_1_5_WHITESPACE(self):
        self.assertEqual('<x y="1" z="2"></x>',
                         render_xml(XMLParser.parse('<x   y = "1"\n z="2"  ></x  >')))

    def test_NBFX_1_5_PI_DTD(self):
        for xml in ('<!DOCTYPE x><x/>', '<x><?pi data?></x>'):
            with self.subTest(xml=xml), self.assertRaises(WcfBinaryError):
                XMLParser.parse(xml)

    def test_NBFX_1_5_XMLDECL(self):
        records = XMLParser.parse('<?xml version="1.0" encoding="utf-8"?><x/>')
        self.assertEqual(1, len(records))
        self.assertEqual('<x></x>', render_xml(records))


class NBFX_1_7_VendorExtensibleFields(unittest.TestCase):

    def test_NBFX_1_7_UNKNOWN_ID(self):
        for wire in (b'\x42\x01\x01', b'\x40\x01a\xab\xce\x07', b'\x40\x01a\xbc\x00\x01\x01'):
            with self.subTest(wire=wire), self.assertRaises(WcfBinaryError):
                decode(wire)
        for make in (lambda: DictionaryTextRecord(1).to_bytes(),
                     lambda: QNameDictionaryTextRecord('a', 0x3CE).to_bytes(),
                     lambda: ShortDictionaryXmlnsAttributeRecord(1)):
            with self.assertRaises(WcfBinaryError):
                make()


# ---------------------------------------------------------------- MC-NBFX 2

class NBFX_2_Structures(unittest.TestCase):

    def test_NBFX_2_ZERO_OR_MORE(self):
        self.assertEqual([], decode(b''))
        self.assertEqual('', render(b''))
        self.assertEqual(b'', dump_records([]))

    def test_NBFX_2_CONCATENATION(self):
        wire = b'\x40\x01a\x98\x01x\x02\x01c\x40\x01b\x01\x01'
        self.assertEqual('<a>' + 'x' + '<!--c-->' + '<b>' + '</b>' + '</a>', render(wire))

    def test_NBFX_2_NOT_NECESSARILY_VALID(self):
        wire = b'\x98\x01t\x40\x01a\x01\x40\x01b\x01'
        self.assertEqual('t<a></a><b></b>', render(wire))
        self.assertEqual(wire, dump_records(decode(wire)))

    def test_NBFX_2_ANY_ORDER(self):
        wire = (b'\x02\x01c' + h('03 40 01 61 01 8B 01 05 00') + b'\xa8' +
                b'\x40\x01r\x02\x01d\x98\x01t\x40\x01e\x01\x01')
        self.assertEqual('<!--c--><a>5</a><r><!--d-->t<e></e></r>', render(wire))
        self.assertEqual(wire, dump_records(decode(wire)))

    def test_NBFX_2_UNCLOSED_ELEMENT(self):
        """Documented deviation: an element still open at the end of the
        document is refused, as the .NET binary reader does."""
        for wire in (b'\x40\x01a', b'\x40\x01a\x98\x01b', b'\x40\x01a\x40\x01b\x01'):
            with self.subTest(wire=wire), self.assertRaisesRegex(WcfBinaryError, 'Unterminated'):
                decode(wire)


class NBFX_2_1_CommonDefinitions(unittest.TestCase):

    def test_NBFX_2_1_LITTLE_ENDIAN(self):
        for record, raw in (
                (Int16TextRecord(0x0102), b'\x02\x01'),
                (Int32TextRecord(0x01020304), b'\x04\x03\x02\x01'),
                (Int64TextRecord(0x0102030405060708), h('08 07 06 05 04 03 02 01')),
                (UInt64TextRecord(0x0102030405060708), h('08 07 06 05 04 03 02 01')),
                (FloatTextRecord(1.0), struct.pack('<f', 1.0)),
                (DoubleTextRecord(1.0), struct.pack('<d', 1.0)),
                (TimeSpanTextRecord(0x0102), h('02 01 00 00 00 00 00 00')),
                (DatetimeTextRecord(0x0102, 0), h('02 01 00 00 00 00 00 00')),
                (Chars16TextRecord('a' * 0x0102), b'\x02\x01' + b'a' * 0x102),
                (Chars32TextRecord('a' * 0x0102), b'\x02\x01\x00\x00' + b'a' * 0x102),
                (Bytes16TextRecord(b'a' * 0x0102), b'\x02\x01' + b'a' * 0x102),
                (UnicodeChars16TextRecord('a' * 0x81), b'\x02\x01' + b'a\x00' * 0x81),
                (DecimalTextRecord(Decimal(False, 0x01020304, 0x05, 2)),
                 h('00 00 02 00 04 03 02 01 05 00 00 00 00 00 00 00'))):
            with self.subTest(record=type(record).__name__):
                self.assertEqual(raw, record.to_bytes()[1:])
                self.assertEqual(record.to_bytes(),
                                 type(record).parse(io.BytesIO(raw)).to_bytes())
        self.assertEqual(0x0102, decode(b'\x40\x01a\x8b\x02\x01')[0].childs[0].value)

    def test_NBFX_2_1_NO_ALIGNMENT(self):
        # fixed-size values at every offset modulo 8
        for pad in range(8):
            name = 'n' * (pad + 1)
            wire = b'\x40' + S(name) + b'\x8f' + h('08 07 06 05 04 03 02 01')
            self.assertEqual('<%s>72623859790382856</%s>' % (name, name), render(wire))


# -------------------------------------------------------------- MC-NBFX 2.1.1

class NBFX_2_1_1_Record(unittest.TestCase):
    """Table 1: every record type, Reserved ones and every letter of the
    Prefix* families included (one generated test per type)."""

    def test_NBFX_2_1_1_RECORDTYPE_ONE_BYTE(self):
        for record_type, cls in Record.records.items():
            self.assertTrue(0 <= record_type <= 0xFF)
            self.assertEqual(record_type, cls.type)

    def test_NBFX_2_1_1_MUST_BE_LISTED(self):
        listed = {t for t, name in RECORD_NAMES.items() if name}
        decodable = set(Record.records)
        decodable |= {t + 1 for t, c in Record.records.items()
                      if issubclass(c, Text) and c.with_end_element}
        self.assertEqual(listed, decodable)
        for t in RESERVED:
            with self.subTest(type='0x%02X' % t), self.assertRaises(WcfBinaryError):
                decode(bytes((t,)))

    def check_record_type(self, t):
        name = RECORD_NAMES[t]
        if name is None:                                    # Reserved
            self.assertNotIn(t, Record.records)
            previous = Record.records.get(t - 1)
            self.assertFalse(previous is not None and issubclass(previous, Text) and
                             previous.with_end_element)
            for wire in (bytes((t,)), b'\x40\x01e' + bytes((t,)) + b'\x01',
                         b'\x40\x01e\x04\x01a' + bytes((t,)) + b'\x01',
                         b'\x40\x01e\xa4' + bytes((t,)) + b'\xa6\x01',
                         b'\x03\x40\x01e\x01' + bytes((t,)) + b'\x01\x00'):
                with self.subTest(wire=wire), self.assertRaises(WcfBinaryError):
                    decode(wire)
            return
        if name.endswith('WithEndElement'):
            self.assertNotIn(t, Record.records)
            text_class = Record.records[t - 1]
            self.assertEqual(_class_name(name[:-len('WithEndElement')]), text_class.__name__)
            payload, chars = TEXT_SAMPLES[t - 1]
            wire = b'\x40\x01e' + bytes((t,)) + payload
            records = decode(wire)
            self.assertEqual('<e>%s</e>' % chars, render_xml(records))
            self.assertEqual('implicit', records[0]._wcf_closure)
            self.assertEqual(wire, dump_records(records))
            element = ShortElementRecord('e')
            element.childs.append(TEXT_FACTORIES[t - 1]())
            self.assertEqual(wire, dump_records([element]))
            # never an attribute value (2.2.3.31)
            with self.assertRaises(WcfBinaryError):
                decode(b'\x40\x01e\x04\x01a' + bytes((t,)) + payload + b'\x01')
            return
        cls = Record.records[t]
        self.assertEqual(_class_name(name), cls.__name__)
        if t == 0x01:
            self.assertEqual(b'\x01', EndElementRecord().to_bytes())
            records = decode(b'\x40\x01e\x01')
            self.assertEqual('explicit', records[0]._wcf_closure)
            self.assertEqual('<e></e>', render_xml(records))
        elif t == 0x02:
            self.assertEqual(b'\x02\x01c', CommentRecord('c').to_bytes())
            self.assertEqual('<!--c-->', render(b'\x02\x01c'))
        elif t == 0x03:
            wire = h('03 40 01 61 01 8D 02 01 00 00 00 02 00 00 00')
            self.assertEqual(wire, ArrayRecord(ShortElementRecord('a'),
                                               [Int32TextRecord(1), Int32TextRecord(2)],
                                               []).to_bytes())
            self.assertEqual('<a>1</a><a>2</a>', render(wire))
        elif issubclass(cls, Attribute):
            fields, chars, factory = ATTRIBUTE_SAMPLES[t]
            record = factory()
            self.assertIs(cls, type(record))
            self.assertEqual(bytes((t,)) + fields, record.to_bytes())
            wire = b'\x40\x01e' + bytes((t,)) + fields + b'\x01'
            self.assertEqual('<e %s></e>' % chars, render(wire))
            self.assertEqual(wire, dump_records(decode(wire)))
        elif issubclass(cls, Element):
            fields, qname, factory = ELEMENT_SAMPLES[t]
            record = factory()
            self.assertIs(cls, type(record))
            self.assertEqual(bytes((t,)) + fields, record.to_bytes())
            wire = bytes((t,)) + fields + b'\x01'
            self.assertEqual('<%s></%s>' % (qname, qname), render(wire))
            self.assertEqual(wire, dump_records(decode(wire)))
        elif t == 0xA6:                                     # EndListText
            self.assertFalse(cls.standalone)
            for wire in (b'\xa6', b'\x40\x01e\xa6\x01', b'\x40\x01e\x04\x01a\xa6\x01'):
                with self.subTest(wire=wire), self.assertRaises(WcfBinaryError):
                    decode(wire)
            self.assertEqual('<e></e>', render(b'\x40\x01e\xa4\xa6\x01'))
            self.assertEqual(b'\xa4\xa6', StartListTextRecord([]).to_bytes())
        else:                                               # text record
            payload, chars = TEXT_SAMPLES[t]
            record = TEXT_FACTORIES[t]()
            self.assertIs(cls, type(record))
            self.assertEqual(bytes((t,)) + payload, record.to_bytes())
            self.assertEqual(chars, str(record))
            for wire, xml in ((b'\x40\x01e' + bytes((t,)) + payload + b'\x01',
                               '<e>%s</e>' % chars),
                              (b'\x40\x01e\x04\x01a' + bytes((t,)) + payload + b'\x01',
                               '<e a="%s"></e>' % chars)):
                with self.subTest(wire=wire):
                    self.assertEqual(xml, render(wire))
                    self.assertEqual(wire, dump_records(decode(wire)))


def _record_type_test(t):
    def test(self):
        self.check_record_type(t)
    test.__doc__ = 'MC-NBFX 2.1.1: 0x%02X is %s' % (t, RECORD_NAMES[t] or 'Reserved')
    return test


for _t in range(0x100):
    setattr(NBFX_2_1_1_Record, 'test_NBFX_2_1_1_RT_%02X' % _t, _record_type_test(_t))


# -------------------------------------------------------------- MC-NBFX 2.1.2

class NBFX_2_1_2_MultiByteInt31(unittest.TestCase):

    def check(self, value, raw):
        self.assertEqual(raw, MultiByteInt31(value).to_bytes())
        self.assertEqual(value, mbi31(raw))

    def test_NBFX_2_1_2_UNSIGNED_31(self):
        self.check(0x7FFFFFFF, h('FF FF FF FF 07'))
        for value in (-1, 1 << 31, 1.0, None):
            with self.subTest(value=value), self.assertRaises(WcfBinaryError):
                MultiByteInt31(value).to_bytes()

    def test_NBFX_2_1_2_SIZE_1(self):
        self.check(0x00, b'\x00')
        self.check(0x7F, b'\x7f')

    def test_NBFX_2_1_2_SIZE_2(self):
        self.check(0x80, h('80 01'))
        self.check(0x3FFF, h('FF 7F'))

    def test_NBFX_2_1_2_SIZE_3(self):
        self.check(0x4000, h('80 80 01'))
        self.check(0x1FFFFF, h('FF FF 7F'))

    def test_NBFX_2_1_2_SIZE_4(self):
        self.check(0x200000, h('80 80 80 01'))
        self.check(0xFFFFFFF, h('FF FF FF 7F'))

    def test_NBFX_2_1_2_SIZE_5(self):
        self.check(0x10000000, h('80 80 80 80 01'))
        self.check(0x7FFFFFFF, h('FF FF FF FF 07'))

    def test_NBFX_2_1_2_1_EX_17(self):
        self.check(17, b'\x11')

    def test_NBFX_2_1_2_2_EX_145(self):
        self.check(145, h('91 01'))

    def test_NBFX_2_1_2_2_EX_5521(self):
        self.check(5521, h('91 2B'))

    def test_NBFX_2_1_2_3_EX_16384(self):
        self.check(16384, h('80 80 01'))

    def test_NBFX_2_1_2_4_EX(self):
        # the published example says 268435456 for 0x80 0x80 0x80 0x01:
        # these 4 bytes are 2097152 (0x200000); 268435456 is 0x10000000,
        # 5 bytes (range table of 2.1.2 and example of 2.1.2.5)
        self.check(2097152, h('80 80 80 01'))
        self.assertEqual(5, len(MultiByteInt31(268435456).to_bytes()))

    def test_NBFX_2_1_2_5_EX_268435456(self):
        self.check(268435456, h('80 80 80 80 01'))

    def test_NBFX_2_1_2_5_VALUE_E_3_BITS(self):
        for fifth in (0x08, 0x10, 0x80, 0xFF):
            with self.subTest(fifth=fifth), self.assertRaises(WcfBinaryError):
                mbi31(h('FF FF FF FF') + bytes((fifth,)))

    def test_NBFX_2_1_2_CANONICAL(self):
        # documented difference: a non-minimal packet is refused
        for raw in ('80 00', '81 00', '80 80 00', '80 80 80 00', '80 80 80 80 00'):
            with self.subTest(raw=raw), self.assertRaises(WcfBinaryError):
                mbi31(h(raw))

    def test_NBFX_2_1_2_TRUNCATED(self):
        for raw in (b'', b'\x80', b'\xff\xff', b'\xff\xff\xff\xff'):
            with self.subTest(raw=raw), self.assertRaises(WcfBinaryError):
                mbi31(raw)


# -------------------------------------------------------------- MC-NBFX 2.1.3

class NBFX_2_1_3_String(unittest.TestCase):

    def test_NBFX_2_1_3_LENGTH_MBI31_BYTES(self):
        raw = Utf8String('é' * 100).to_bytes()
        self.assertEqual(MultiByteInt31(200).to_bytes(), raw[:2])
        self.assertEqual('é' * 100, Utf8String.parse(io.BytesIO(raw)).value)

    def test_NBFX_2_1_3_UTF8(self):
        for raw in (b'\x01\xff', b'\x02\xc3\x28', b'\x01\xc3', b'\x03\xed\xa0\x80'):
            with self.subTest(raw=raw), self.assertRaises(WcfBinaryError):
                decode(b'\x40' + raw + b'\x01')
        with self.assertRaises(ValueError):
            Utf8String('\ud800').to_bytes()

    def test_NBFX_2_1_3_EX_ABC(self):
        self.assertEqual(h('03 61 62 63'), Utf8String('abc').to_bytes())
        self.assertEqual('abc', Utf8String.parse(io.BytesIO(h('03 61 62 63'))).value)

    def test_NBFX_2_1_3_NO_RESTRICTION(self):
        # any character is decoded and encoded again; render_xml() refuses
        # what XML cannot carry (documented)
        for wire in (b'\x02\x03a\x00b', b'\x40\x03a b\x01'):
            with self.subTest(wire=wire):
                records = decode(wire)
                self.assertEqual(wire, dump_records(records))
                with self.assertRaises(WcfBinaryError):
                    render_xml(records)


class NBFX_2_1_4_DictionaryString(unittest.TestCase):

    def test_NBFX_2_1_4_MBI31(self):
        self.assertEqual(b'\xaa\xcc\x07', DictionaryTextRecord(0x3CC).to_bytes())
        self.assertEqual('<a>detail</a>', render(b'\x40\x01a\xab\xcc\x07'))

    def test_NBFX_2_1_4_MAPPING(self):
        with dictionary_context({1: 'hello'}):
            self.assertEqual('<a>hello</a>', render(b'\x40\x01a\xab\x01'))
        with self.assertRaises(WcfBinaryError):
            decode(b'\x40\x01a\xab\x01')

    def test_NBFX_2_1_4_NO_RESTRICTION(self):
        with dictionary_context({1: '<&"\x01'}):
            self.assertEqual('<a b="&lt;&amp;&quot;&#1;">&lt;&amp;"&#1;</a>',
                             render(b'\x40\x01a\x04\x01b\xaa\x01\xab\x01'))


# ---------------------------------------------------------------- MC-NBFX 2.2

class NBFX_2_2_Records(unittest.TestCase):

    def test_NBFX_2_2_EXACT_CASING(self):
        for record, chars in ((TrueTextRecord(), 'true'), (FalseTextRecord(), 'false'),
                              (BoolTextRecord(False), 'false'),
                              (DoubleTextRecord(float('inf')), 'INF'),
                              (DoubleTextRecord(float('-inf')), '-INF'),
                              (FloatTextRecord(float('nan')), 'NaN'),
                              (DoubleTextRecord(1e300), '1E+300'),
                              (UuidTextRecord(_UUID.upper()), _UUID),
                              (UniqueIdTextRecord(_UUID.upper()), 'urn:uuid:' + _UUID)):
            with self.subTest(chars=chars):
                self.assertEqual(chars, str(record))


class NBFX_2_2_1_ElementRecords(unittest.TestCase):

    def refused(self, *wires):
        for wire in wires:
            with self.subTest(wire=wire), self.assertRaises(WcfBinaryError):
                decode(wire)

    def test_NBFX_2_2_1_RANGE(self):
        for t in range(0x100):
            cls = Record.records.get(t)
            self.assertEqual(0x40 <= t <= 0x77,
                             cls is not None and issubclass(cls, Element), hex(t))

    def test_NBFX_2_2_1_ATTRIBUTES_ZERO_OR_MORE(self):
        for count in (0, 1, 3):
            element = ShortElementRecord('e')
            element.attributes.extend(ShortAttributeRecord('a%d' % i, TrueTextRecord())
                                      for i in range(count))
            wire = dump_records([element])
            self.assertEqual(wire, b'\x40\x01e' + b''.join(
                b'\x04\x02a%d\x86' % i for i in range(count)) + b'\x01')
            self.assertEqual(count, len(decode(wire)[0].attributes))

    # 2.2.1.1 ShortElement
    def test_NBFX_2_2_1_1_NAME_NONZERO(self):
        self.refused(b'\x40\x00\x01')
        with self.assertRaises(WcfBinaryError):
            ShortElementRecord('')

    def test_NBFX_2_2_1_1_NAME_NOT_XMLNS(self):
        self.refused(b'\x40\x05xmlns\x01')
        with self.assertRaises(WcfBinaryError):
            ShortElementRecord('xmlns')

    def test_NBFX_2_2_1_1_EX(self):
        self.assertEqual('<element xmlns="http://tempuri.org"></element>',
                         render(b'\x40' + S('element') + b'\x08' + S('http://tempuri.org') + b'\x01'))

    # 2.2.1.2 Element
    def test_NBFX_2_2_1_2_PREFIX_NONZERO(self):
        self.refused(b'\x41\x00\x01e\x01')
        with self.assertRaises(WcfBinaryError):
            ElementRecord('', 'e')

    def test_NBFX_2_2_1_2_PREFIX_NOT_XMLNS(self):
        self.refused(b'\x41\x05xmlns\x01e\x01')
        with self.assertRaises(WcfBinaryError):
            ElementRecord('xmlns', 'e')

    def test_NBFX_2_2_1_2_NAME_NONZERO(self):
        self.refused(b'\x41\x01p\x00\x01')
        with self.assertRaises(WcfBinaryError):
            ElementRecord('p', '')

    def test_NBFX_2_2_1_2_NAME_NOT_XMLNS(self):
        self.refused(b'\x41\x01p\x05xmlns\x01')
        with self.assertRaises(WcfBinaryError):
            ElementRecord('p', 'xmlns')

    def test_NBFX_2_2_1_2_EX(self):
        self.assertEqual(
            '<prefix:element xmlns:prefix="http://tempuri.org"></prefix:element>',
            render(b'\x41' + S('prefix') + S('element') + b'\x09' + S('prefix') +
                   S('http://tempuri.org') + b'\x01'))

    # 2.2.1.3 ShortDictionaryElement (static 0xA2 is the empty string)
    def test_NBFX_2_2_1_3_NAME_NONZERO(self):
        self.refused(b'\x42\xa2\x01\x01')
        with self.assertRaises(WcfBinaryError):
            ShortDictionaryElementRecord(0xA2)

    def test_NBFX_2_2_1_3_NAME_NOT_XMLNS(self):
        with dictionary_context({1: 'xmlns'}):
            self.refused(b'\x42\x01\x01')
            with self.assertRaises(WcfBinaryError):
                ShortDictionaryElementRecord(1)

    def test_NBFX_2_2_1_3_EX(self):
        with dictionary_context({1: 'element'}):
            self.assertEqual('<element xmlns="http://tempuri.org"></element>',
                             render(b'\x42\x01\x08' + S('http://tempuri.org') + b'\x01'))

    # 2.2.1.4 DictionaryElement
    def test_NBFX_2_2_1_4_PREFIX_NONZERO(self):
        self.refused(b'\x43\x00\x02\x01')
        with self.assertRaises(WcfBinaryError):
            DictionaryElementRecord('', 2)

    def test_NBFX_2_2_1_4_PREFIX_NOT_XMLNS(self):
        self.refused(b'\x43\x05xmlns\x02\x01')
        with self.assertRaises(WcfBinaryError):
            DictionaryElementRecord('xmlns', 2)

    def test_NBFX_2_2_1_4_NAME_NONZERO(self):
        self.refused(b'\x43\x01p\xa2\x01\x01')
        with self.assertRaises(WcfBinaryError):
            DictionaryElementRecord('p', 0xA2)

    def test_NBFX_2_2_1_4_NAME_NOT_XMLNS(self):
        with dictionary_context({1: 'xmlns'}):
            self.refused(b'\x43\x01p\x01\x01')
            with self.assertRaises(WcfBinaryError):
                DictionaryElementRecord('p', 1)

    def test_NBFX_2_2_1_4_EX(self):
        with dictionary_context({1: 'element'}):
            self.assertEqual(
                '<prefix:element xmlns:prefix="http://tempuri.org"></prefix:element>',
                render(b'\x43' + S('prefix') + b'\x01\x09' + S('prefix') +
                       S('http://tempuri.org') + b'\x01'))

    # 2.2.1.5 PrefixDictionaryElement[A-Z]
    def test_NBFX_2_2_1_5_NAME_NONZERO(self):
        for letter, cls in PREFIX_DICTIONARY_ELEMENTS.items():
            self.refused(bytes((cls.type,)) + b'\xa2\x01\x01')
            with self.assertRaises(WcfBinaryError):
                cls(0xA2)

    def test_NBFX_2_2_1_5_NAME_NOT_XMLNS(self):
        with dictionary_context({1: 'xmlns'}):
            for letter, cls in PREFIX_DICTIONARY_ELEMENTS.items():
                self.refused(bytes((cls.type,)) + b'\x01\x01')
                with self.assertRaises(WcfBinaryError):
                    cls(1)

    def test_NBFX_2_2_1_5_PREFIX_FROM_TYPE(self):
        for i, letter in enumerate('abcdefghijklmnopqrstuvwxyz'):
            cls = PREFIX_DICTIONARY_ELEMENTS[letter]
            self.assertEqual(0x44 + i, cls.type)
            self.assertEqual(letter, decode(bytes((0x44 + i,)) + b'\x02\x01')[0].prefix)

    def test_NBFX_2_2_1_5_EX(self):
        with dictionary_context({1: 'element'}):
            self.assertEqual('<b:element xmlns:b="http://tempuri.org"></b:element>',
                             render(b'\x45\x01\x09\x01b' + S('http://tempuri.org') + b'\x01'))

    # 2.2.1.6 PrefixElement[A-Z]
    def test_NBFX_2_2_1_6_NAME_NONZERO(self):
        for letter, cls in PREFIX_ELEMENTS.items():
            self.refused(bytes((cls.type,)) + b'\x00\x01')
            with self.assertRaises(WcfBinaryError):
                cls('')

    def test_NBFX_2_2_1_6_NAME_NOT_XMLNS(self):
        for letter, cls in PREFIX_ELEMENTS.items():
            self.refused(bytes((cls.type,)) + b'\x05xmlns\x01')
            with self.assertRaises(WcfBinaryError):
                cls('xmlns')

    def test_NBFX_2_2_1_6_PREFIX_FROM_TYPE(self):
        for i, letter in enumerate('abcdefghijklmnopqrstuvwxyz'):
            cls = PREFIX_ELEMENTS[letter]
            self.assertEqual(0x5E + i, cls.type)
            self.assertEqual(letter, decode(bytes((0x5E + i,)) + b'\x01e\x01')[0].prefix)

    def test_NBFX_2_2_1_6_EX(self):
        self.assertEqual('<b:element xmlns:b="http://tempuri.org"></b:element>',
                         render(b'\x5f' + S('element') + b'\x09\x01b' +
                                S('http://tempuri.org') + b'\x01'))


class NBFX_2_2_2_AttributeRecords(unittest.TestCase):

    def refused(self, *wires):
        for wire in wires:
            with self.subTest(wire=wire), self.assertRaises(WcfBinaryError):
                decode(wire)

    def in_element(self, attribute):
        return b'\x40\x01e' + attribute + b'\x01'

    def test_NBFX_2_2_2_RANGE(self):
        for t in range(0x100):
            cls = Record.records.get(t)
            self.assertEqual(0x04 <= t <= 0x3F,
                             cls is not None and issubclass(cls, Attribute), hex(t))

    def test_NBFX_2_2_2_FOLLOW(self):
        attribute = b'\x04\x01a\x86'
        self.refused(attribute,                                   # no element
                     b'\x40\x01e\x98\x01t' + attribute + b'\x01',  # after text
                     b'\x40\x01e\x02\x01c' + attribute + b'\x01',  # after a comment
                     b'\x40\x01e\x40\x01f\x01' + attribute + b'\x01',  # after a child
                     b'\x40\x01e\x01' + attribute)                 # after EndElement
        self.assertEqual('<e a="true" b="true"></e>',
                         render(b'\x40\x01e' + attribute + b'\x04\x01b\x86\x01'))

    def check_value_text(self, header):
        """The Value of an attribute is one text record."""
        self.refused(self.in_element(header + b'\x40\x01x\x01'),   # element
                     self.in_element(header + b'\x02\x01c'),       # comment
                     self.in_element(header + b'\xa6'),            # EndListText
                     self.in_element(header + b'\x87'),            # *WithEndElement
                     self.in_element(header + b'\x01'),            # EndElement
                     self.in_element(header))                      # missing
        for t, (payload, chars) in TEXT_SAMPLES.items():
            self.assertEqual('<e %s></e>' % self.rendered_name(header, chars),
                             render(self.in_element(header + bytes((t,)) + payload)))

    names = {0x04: 'a', 0x05: 'p:a', 0x06: 'Envelope', 0x07: 'p:Envelope'}

    def rendered_name(self, header, chars):
        t = header[0]
        if 0x0C <= t <= 0x25:
            name = '%s:Envelope' % chr(ord('a') + t - 0x0C)
        elif 0x26 <= t <= 0x3F:
            name = '%s:a' % chr(ord('a') + t - 0x26)
        else:
            name = self.names[t]
        return '%s="%s"' % (name, chars)

    # 2.2.2.1 ShortAttribute
    def test_NBFX_2_2_2_1_NAME_NONZERO(self):
        self.refused(self.in_element(b'\x04\x00\x86'))
        with self.assertRaises(WcfBinaryError):
            ShortAttributeRecord('', TrueTextRecord())

    def test_NBFX_2_2_2_1_NAME_NOT_XMLNS(self):
        self.refused(self.in_element(b'\x04\x05xmlns\x86'))
        with self.assertRaises(WcfBinaryError):
            ShortAttributeRecord('xmlns', TrueTextRecord())

    def test_NBFX_2_2_2_1_VALUE_TEXT(self):
        self.check_value_text(b'\x04\x01a')
        with self.assertRaises(WcfBinaryError):
            ShortAttributeRecord('a', ShortElementRecord('x'))

    def test_NBFX_2_2_2_1_EX(self):
        self.assertEqual('<e attr="value"></e>',
                         render(self.in_element(b'\x04' + S('attr') + b'\x98' + S('value'))))

    # 2.2.2.2 Attribute
    def test_NBFX_2_2_2_2_PREFIX_NONZERO(self):
        self.refused(self.in_element(b'\x05\x00\x01a\x86'))
        with self.assertRaises(WcfBinaryError):
            AttributeRecord('', 'a', TrueTextRecord())

    def test_NBFX_2_2_2_2_PREFIX_NOT_XMLNS(self):
        self.refused(self.in_element(b'\x05\x05xmlns\x01a\x86'))
        with self.assertRaises(WcfBinaryError):
            AttributeRecord('xmlns', 'a', TrueTextRecord())

    def test_NBFX_2_2_2_2_NAME_NONZERO(self):
        self.refused(self.in_element(b'\x05\x01p\x00\x86'))
        with self.assertRaises(WcfBinaryError):
            AttributeRecord('p', '', TrueTextRecord())

    def test_NBFX_2_2_2_2_NAME_NOT_XMLNS(self):
        self.refused(self.in_element(b'\x05\x01p\x05xmlns\x86'))
        with self.assertRaises(WcfBinaryError):
            AttributeRecord('p', 'xmlns', TrueTextRecord())

    def test_NBFX_2_2_2_2_VALUE_TEXT(self):
        self.check_value_text(b'\x05\x01p\x01a')

    def test_NBFX_2_2_2_2_EX(self):
        self.assertEqual('<e prefix:attr="value"></e>', render(self.in_element(
            b'\x05' + S('prefix') + S('attr') + b'\x98' + S('value'))))

    # 2.2.2.3 ShortDictionaryAttribute
    def test_NBFX_2_2_2_3_NAME_NONZERO(self):
        self.refused(self.in_element(b'\x06\xa2\x01\x86'))
        with self.assertRaises(WcfBinaryError):
            ShortDictionaryAttributeRecord(0xA2, TrueTextRecord())

    def test_NBFX_2_2_2_3_NAME_NOT_XMLNS(self):
        with dictionary_context({1: 'xmlns'}):
            self.refused(self.in_element(b'\x06\x01\x86'))
            with self.assertRaises(WcfBinaryError):
                ShortDictionaryAttributeRecord(1, TrueTextRecord())

    def test_NBFX_2_2_2_3_VALUE_TEXT(self):
        self.check_value_text(b'\x06\x02')

    def test_NBFX_2_2_2_3_EX(self):
        with dictionary_context({1: 'attr'}):
            self.assertEqual('<e attr="value"></e>',
                             render(self.in_element(b'\x06\x01\x98' + S('value'))))

    # 2.2.2.4 DictionaryAttribute
    def test_NBFX_2_2_2_4_PREFIX_NONZERO(self):
        self.refused(self.in_element(b'\x07\x00\x02\x86'))
        with self.assertRaises(WcfBinaryError):
            DictionaryAttributeRecord('', 2, TrueTextRecord())

    def test_NBFX_2_2_2_4_PREFIX_NOT_XMLNS(self):
        self.refused(self.in_element(b'\x07\x05xmlns\x02\x86'))
        with self.assertRaises(WcfBinaryError):
            DictionaryAttributeRecord('xmlns', 2, TrueTextRecord())

    def test_NBFX_2_2_2_4_NAME_NONZERO(self):
        self.refused(self.in_element(b'\x07\x01p\xa2\x01\x86'))
        with self.assertRaises(WcfBinaryError):
            DictionaryAttributeRecord('p', 0xA2, TrueTextRecord())

    def test_NBFX_2_2_2_4_NAME_NOT_XMLNS(self):
        with dictionary_context({1: 'xmlns'}):
            self.refused(self.in_element(b'\x07\x01p\x01\x86'))
            with self.assertRaises(WcfBinaryError):
                DictionaryAttributeRecord('p', 1, TrueTextRecord())

    def test_NBFX_2_2_2_4_VALUE_TEXT(self):
        self.check_value_text(b'\x07\x01p\x02')

    def test_NBFX_2_2_2_4_EX(self):
        with dictionary_context({1: 'attr'}):
            self.assertEqual('<e prefix:attr="value"></e>', render(self.in_element(
                b'\x07' + S('prefix') + b'\x01\x98' + S('value'))))

    # 2.2.2.5 ShortXmlnsAttribute
    def test_NBFX_2_2_2_5_VALUE_STRING(self):
        record = decode(self.in_element(b'\x08' + S('urn:é')))[0].attributes[0]
        self.assertEqual('urn:é', record.namespace)
        self.assertEqual(b'\x08' + S('urn:é'), ShortXmlnsAttributeRecord('urn:é').to_bytes())

    def test_NBFX_2_2_2_5_EX(self):
        self.assertEqual('<e xmlns="http://tempuri.org"></e>',
                         render(self.in_element(b'\x08' + S('http://tempuri.org'))))

    # 2.2.2.6 XmlnsAttribute
    def test_NBFX_2_2_2_6_PREFIX_NONZERO(self):
        self.refused(self.in_element(b'\x09\x00' + S('urn:x')))
        with self.assertRaises(WcfBinaryError):
            XmlnsAttributeRecord('', 'urn:x')

    def test_NBFX_2_2_2_6_PREFIX_NOT_XMLNS(self):
        self.refused(self.in_element(b'\x09\x05xmlns' + S('urn:x')))
        with self.assertRaises(WcfBinaryError):
            XmlnsAttributeRecord('xmlns', 'urn:x')

    def test_NBFX_2_2_2_6_VALUE_STRING(self):
        self.assertEqual(b'\x09\x01p' + S('urn:é'), XmlnsAttributeRecord('p', 'urn:é').to_bytes())
        self.assertEqual('urn:é', decode(self.in_element(
            b'\x09\x01p' + S('urn:é')))[0].attributes[0].namespace)

    def test_NBFX_2_2_2_6_EX(self):
        self.assertEqual('<e xmlns:ENV="http://tempuri.org"></e>', render(self.in_element(
            b'\x09' + S('ENV') + S('http://tempuri.org'))))

    # 2.2.2.7 ShortDictionaryXmlnsAttribute
    def test_NBFX_2_2_2_7_VALUE_DICTIONARYSTRING(self):
        self.assertEqual(b'\x0a\xcc\x07', ShortDictionaryXmlnsAttributeRecord(0x3CC).to_bytes())
        self.assertEqual('detail', decode(self.in_element(b'\x0a\xcc\x07'))[0]
                         .attributes[0].namespace)

    def test_NBFX_2_2_2_7_EX(self):
        with dictionary_context({1: 'value'}):
            self.assertEqual('<e xmlns="value"></e>', render(self.in_element(b'\x0a\x01')))

    # 2.2.2.8 DictionaryXmlnsAttribute
    def test_NBFX_2_2_2_8_PREFIX_NONZERO(self):
        self.refused(self.in_element(b'\x0b\x00\x06'))
        with self.assertRaises(WcfBinaryError):
            DictionaryXmlnsAttributeRecord('', 6)

    def test_NBFX_2_2_2_8_PREFIX_NOT_XMLNS(self):
        self.refused(self.in_element(b'\x0b\x05xmlns\x06'))
        with self.assertRaises(WcfBinaryError):
            DictionaryXmlnsAttributeRecord('xmlns', 6)

    def test_NBFX_2_2_2_8_VALUE_DICTIONARYSTRING(self):
        self.assertEqual(b'\x0b\x01p\xcc\x07', DictionaryXmlnsAttributeRecord('p', 0x3CC).to_bytes())

    def test_NBFX_2_2_2_8_EX(self):
        with dictionary_context({1: 'http://tempuri.org'}):
            self.assertEqual('<e xmlns:ENV="http://tempuri.org"></e>',
                             render(self.in_element(b'\x0b' + S('ENV') + b'\x01')))

    # 2.2.2.9 PrefixDictionaryAttribute[A-Z]
    def test_NBFX_2_2_2_9_NAME_NONZERO(self):
        for cls in PREFIX_DICTIONARY_ATTRIBUTES.values():
            self.refused(self.in_element(bytes((cls.type,)) + b'\xa2\x01\x86'))
            with self.assertRaises(WcfBinaryError):
                cls(0xA2, TrueTextRecord())

    def test_NBFX_2_2_2_9_NAME_NOT_XMLNS(self):
        with dictionary_context({1: 'xmlns'}):
            for cls in PREFIX_DICTIONARY_ATTRIBUTES.values():
                self.refused(self.in_element(bytes((cls.type,)) + b'\x01\x86'))
                with self.assertRaises(WcfBinaryError):
                    cls(1, TrueTextRecord())

    def test_NBFX_2_2_2_9_VALUE_TEXT(self):
        for cls in PREFIX_DICTIONARY_ATTRIBUTES.values():
            with self.subTest(cls=cls.__name__):
                self.check_value_text(bytes((cls.type,)) + b'\x02')

    def test_NBFX_2_2_2_9_PREFIX_FROM_TYPE(self):
        for i, letter in enumerate('abcdefghijklmnopqrstuvwxyz'):
            cls = PREFIX_DICTIONARY_ATTRIBUTES[letter]
            self.assertEqual(0x0C + i, cls.type)
            self.assertEqual('<e %s:Envelope="true"></e>' % letter,
                             render(self.in_element(bytes((0x0C + i,)) + b'\x02\x86')))

    # 2.2.2.10 PrefixAttribute[A-Z]
    def test_NBFX_2_2_2_10_NAME_NONZERO(self):
        for cls in PREFIX_ATTRIBUTES.values():
            self.refused(self.in_element(bytes((cls.type,)) + b'\x00\x86'))
            with self.assertRaises(WcfBinaryError):
                cls('', TrueTextRecord())

    def test_NBFX_2_2_2_10_NAME_NOT_XMLNS(self):
        for cls in PREFIX_ATTRIBUTES.values():
            self.refused(self.in_element(bytes((cls.type,)) + b'\x05xmlns\x86'))
            with self.assertRaises(WcfBinaryError):
                cls('xmlns', TrueTextRecord())

    def test_NBFX_2_2_2_10_VALUE_TEXT(self):
        for cls in PREFIX_ATTRIBUTES.values():
            with self.subTest(cls=cls.__name__):
                self.check_value_text(bytes((cls.type,)) + b'\x01a')

    def test_NBFX_2_2_2_10_PREFIX_FROM_TYPE(self):
        for i, letter in enumerate('abcdefghijklmnopqrstuvwxyz'):
            cls = PREFIX_ATTRIBUTES[letter]
            self.assertEqual(0x26 + i, cls.type)
            self.assertEqual(letter, decode(self.in_element(
                bytes((0x26 + i,)) + b'\x01a\x86'))[0].attributes[0].prefix)

    def test_NBFX_2_2_2_10_EX(self):
        self.assertEqual('<e x:attr="value"></e>', render(self.in_element(
            b'\x3d' + S('attr') + b'\x98' + S('value'))))


# -------------------------------------------------------------- MC-NBFX 2.2.3

def content(t, payload=b''):
    """<a> + one text record + </a>"""
    return render(b'\x40\x01a' + bytes((t,)) + payload + b'\x01')[3:-4]


def attribute_value(t, payload=b''):
    return render(b'\x40\x01a\x04\x01v' + bytes((t,)) + payload + b'\x01')[6:-6]


class NBFX_2_2_3_TextRecords(unittest.TestCase):

    def test_NBFX_2_2_3_RANGE(self):
        for t in range(0x100):
            cls = Record.records.get(t)
            is_text = cls is not None and issubclass(cls, Text)
            with_end = (t & 1 and Record.records.get(t - 1) is not None and
                        issubclass(Record.records[t - 1], Text) and
                        Record.records[t - 1].with_end_element)
            self.assertEqual(0x80 <= t <= 0xBD and t not in (0xA5, 0xA7),
                             bool(is_text or with_end), hex(t))

    def test_NBFX_2_2_3_ATTRIBUTE_OR_ELEMENT_CONTENT(self):
        for t, (payload, chars) in TEXT_SAMPLES.items():
            with self.subTest(type='0x%02X' % t):
                self.assertEqual(chars, content(t, payload))
                self.assertEqual(chars, attribute_value(t, payload))


class NBFX_2_2_3_01_04_ConstantText(unittest.TestCase):

    def test_NBFX_2_2_3_1_CHARS(self):
        self.assertEqual('0', content(0x80))
        self.assertEqual('0', attribute_value(0x80))

    def test_NBFX_2_2_3_1_NO_FIELDS(self):
        self.assertEqual('<a>0<b></b></a>', render(b'\x40\x01a\x80\x40\x01b\x01\x01'))
        self.assertEqual(b'\x80', ZeroTextRecord().to_bytes())

    def test_NBFX_2_2_3_2_CHARS(self):
        self.assertEqual('1', content(0x82))

    def test_NBFX_2_2_3_2_NO_FIELDS(self):
        self.assertEqual(b'\x82', OneTextRecord().to_bytes())
        self.assertEqual('<a>1<b></b></a>', render(b'\x40\x01a\x82\x40\x01b\x01\x01'))

    def test_NBFX_2_2_3_3_CHARS(self):
        self.assertEqual('false', content(0x84))

    def test_NBFX_2_2_3_3_NO_FIELDS(self):
        self.assertEqual(b'\x84', FalseTextRecord().to_bytes())
        self.assertEqual('<a>false<b></b></a>', render(b'\x40\x01a\x84\x40\x01b\x01\x01'))

    def test_NBFX_2_2_3_4_CHARS(self):
        self.assertEqual('true', content(0x86))

    def test_NBFX_2_2_3_4_NO_FIELDS(self):
        self.assertEqual(b'\x86', TrueTextRecord().to_bytes())
        self.assertEqual('<a>true<b></b></a>', render(b'\x40\x01a\x86\x40\x01b\x01\x01'))


class NBFX_2_2_3_05_08_IntText(unittest.TestCase):

    cases = ((0x88, Int8TextRecord, 1), (0x8A, Int16TextRecord, 2),
             (0x8C, Int32TextRecord, 4), (0x8E, Int64TextRecord, 8))

    def check_size(self, t, cls, size):
        for value in (-(1 << (8 * size - 1)), -1, 0, (1 << (8 * size - 1)) - 1):
            raw = value.to_bytes(size, 'little', signed=True)
            self.assertEqual(bytes((t,)) + raw, cls(value).to_bytes())
            self.assertEqual(value, cls.parse(io.BytesIO(raw)).value)
        for value in (-(1 << (8 * size - 1)) - 1, 1 << (8 * size - 1)):
            with self.assertRaises(WcfBinaryError):
                cls(value).to_bytes()

    def check_chars(self, t, size):
        for value, chars in ((0, '0'), (5, '5'), (-5, '-5'), (100, '100'),
                             ((1 << (8 * size - 1)) - 1, str((1 << (8 * size - 1)) - 1))):
            self.assertEqual(chars, content(t, value.to_bytes(size, 'little', signed=True)))

    def test_NBFX_2_2_3_5_SIZE(self):
        self.check_size(*self.cases[0])

    def test_NBFX_2_2_3_5_CHARS(self):
        self.check_chars(0x88, 1)

    def test_NBFX_2_2_3_5_EX(self):
        self.assertEqual('-128', content(0x88, b'\x80'))

    def test_NBFX_2_2_3_6_SIZE(self):
        self.check_size(*self.cases[1])

    def test_NBFX_2_2_3_6_CHARS(self):
        self.check_chars(0x8A, 2)

    def test_NBFX_2_2_3_6_EX(self):
        self.assertEqual('-32768', content(0x8A, h('00 80')))

    def test_NBFX_2_2_3_7_SIZE(self):
        self.check_size(*self.cases[2])

    def test_NBFX_2_2_3_7_CHARS(self):
        self.check_chars(0x8C, 4)

    def test_NBFX_2_2_3_7_EX(self):
        self.assertEqual('-2147483648', content(0x8C, h('00 00 00 80')))

    def test_NBFX_2_2_3_8_SIZE(self):
        self.check_size(*self.cases[3])

    def test_NBFX_2_2_3_8_CHARS(self):
        self.check_chars(0x8E, 8)

    def test_NBFX_2_2_3_8_EX(self):
        self.assertEqual('-9223372036854775808', content(0x8E, h('00 00 00 00 00 00 00 80')))


class NBFX_2_2_3_09_10_FloatDoubleText(unittest.TestCase):

    records = ((FloatTextRecord, '<f', 0x90), (DoubleTextRecord, '<d', 0x92))

    def test_NBFX_2_2_3_9_SIZE(self):
        self.assertEqual(b'\x90' + struct.pack('<f', 1.5), FloatTextRecord(1.5).to_bytes())
        self.assertEqual(1.5, FloatTextRecord.parse(io.BytesIO(struct.pack('<f', 1.5))).value)

    def test_NBFX_2_2_3_10_SIZE(self):
        self.assertEqual(b'\x92' + struct.pack('<d', 1.5), DoubleTextRecord(1.5).to_bytes())

    def check_all(self, check):
        for cls, fmt, t in self.records:
            with self.subTest(record=cls.__name__):
                check(cls, fmt, t)

    def test_NBFX_2_2_3_9_10_POINT_ONLY_IF_FRACTION(self):
        def check(cls, fmt, t):
            self.assertEqual('1', str(cls(1.0)))
            self.assertEqual('12345', str(cls(12345.0)))
            self.assertEqual('1.5', str(cls(1.5)))
        self.check_all(check)

    def test_NBFX_2_2_3_9_10_LEAST_DIGITS(self):
        import random
        rng = random.Random(9)

        def check(cls, fmt, t):
            for _ in range(3000):
                raw = rng.getrandbits(8 * struct.calcsize(fmt)).to_bytes(
                    struct.calcsize(fmt), 'little')
                value = struct.unpack(fmt, raw)[0]
                if value != value:
                    continue
                text = str(cls(value))
                self.assertEqual(raw, struct.pack(fmt, float(text)))
                digits = text.lstrip('-').split('E')[0].replace('.', '').lstrip('0')
                if len(digits) > 1:   # one digit fewer does not reproduce the bits
                    shorter = format(float(text), '.%de' % (len(digits) - 2))
                    self.assertNotEqual(raw, struct.pack(fmt, float(shorter)), text)
        self.check_all(check)

    def test_NBFX_2_2_3_9_10_NO_UNNECESSARY_ZEROS(self):
        def check(cls, fmt, t):
            for value, text in ((0.5, '0.5'), (-0.25, '-0.25'), (1.25, '1.25'),
                                (10.5, '10.5')):
                self.assertEqual(text, str(cls(value)))
        self.check_all(check)

    def test_NBFX_2_2_3_9_10_EXPONENT(self):
        def check(cls, fmt, t):
            for value, text in ((1e20, '1E+20'), (1e-7, '1E-7'), (-1.5e-10, '-1.5E-10'),
                                (1.25e30, '1.25E+30')):
                self.assertEqual(text, str(cls(value)))
        self.check_all(check)

    def test_NBFX_2_2_3_9_10_SPECIAL_VALUES(self):
        def check(cls, fmt, t):
            for value, text in ((float('inf'), 'INF'), (float('-inf'), '-INF'),
                                (float('nan'), 'NaN'), (-0.0, '-0')):
                self.assertEqual(text, content(t, struct.pack(fmt, value)))
        self.check_all(check)

    def test_NBFX_2_2_3_9_10_EXPONENT_100(self):
        # documented difference with .NET: the text of 2.2.3.9 is followed
        self.assertEqual('1E+2', str(FloatTextRecord(100.0)))
        self.assertEqual('1E+2', str(DoubleTextRecord(100.0)))

    def test_NBFX_2_2_3_9_EX(self):
        self.assertEqual('1.1', content(0x90, struct.pack('<I', 0x3F8CCCCD)))

    def test_NBFX_2_2_3_10_EX(self):
        # 0x4005BF0A8B145774 is 2.71828182845905 (as in section 3); the
        # "2.7182818284590451" printed in 2.2.3.10 is 0x4005BF0A8B145769
        raw = struct.pack('<Q', 0x4005BF0A8B145774)
        self.assertEqual('2.71828182845905', content(0x92, raw))
        self.assertNotEqual(raw, struct.pack('<d', 2.7182818284590451))


class NBFX_2_2_3_11_DecimalText(unittest.TestCase):

    def test_NBFX_2_2_3_11_SIZE(self):
        raw = h('00 00 06 80 00 00 00 00 80 2D 4E 00 00 00 00 00')
        record = DecimalTextRecord.parse(io.BytesIO(raw))
        self.assertEqual((True, 0, 5123456, 6), (record.value.sign, record.value.high,
                                                 record.value.low, record.value.scale))
        self.assertEqual(b'\x94' + raw, record.to_bytes())
        self.assertEqual(17, len(DecimalTextRecord(Decimal(False, 1, 1, 0)).to_bytes()))

    def test_NBFX_2_2_3_11_VALID(self):
        for raw in ('00 00 1D 00' + ' 00' * 12, '00 00 00 01' + ' 00' * 12):
            with self.subTest(raw=raw), self.assertRaises(WcfBinaryError):
                decode(b'\x40\x01a\x94' + h(raw) + b'\x01')

    def test_NBFX_2_2_3_11_POINT_ONLY_IF_FRACTION(self):
        self.assertEqual('5', str(Decimal(False, 0, 5, 0)))
        self.assertEqual('1.5', str(Decimal(False, 0, 15, 1)))

    def test_NBFX_2_2_3_11_LEADING_ZERO(self):
        self.assertEqual('0.001', str(Decimal(False, 0, 1, 3)))
        self.assertEqual('-0.5', str(Decimal(True, 0, 5, 1)))

    def test_NBFX_2_2_3_11_TRAILING_ZEROS(self):
        # documented: the scale is part of the DECIMAL and is written (.NET)
        self.assertEqual('1.50', str(Decimal(False, 0, 150, 2)))
        self.assertEqual('1.5', str(Decimal(False, 0, 15, 1)))
        self.assertEqual('<a>1.00</a>', render(b'\x40\x01a\x95' + Decimal(False, 0, 100, 2).to_bytes()))

    def test_NBFX_2_2_3_11_EX(self):
        # the 128-bit value of the example, little-endian on the wire, is
        # wReserved=0, scale=6, sign=0, Hi32=0, Lo64=0x4F2D80: 5.188992.
        # 5.123456 is Lo64=0x4E2D80, the bytes "80 2D 4E" of section 3
        # (DecimalText row): the "4F" of 2.2.3.11 is a typo.
        printed = (0x00000000004F2D800000000000060000).to_bytes(16, 'little')
        self.assertEqual('5.188992', content(0x94, printed))
        corrected = (0x00000000004E2D800000000000060000).to_bytes(16, 'little')
        self.assertEqual('5.123456', content(0x94, corrected))
        self.assertEqual(b'\x94' + corrected,
                         DecimalTextRecord(Decimal(False, 0, 5123456, 6)).to_bytes())


class NBFX_2_2_3_12_DateTimeText(unittest.TestCase):

    def test_NBFX_2_2_3_12_LAYOUT(self):
        self.assertEqual(b'\x96' + struct.pack('<Q', 632834208000000000 | 1 << 62),
                         DatetimeTextRecord(632834208000000000, 1).to_bytes())
        record = DatetimeTextRecord.parse(io.BytesIO(struct.pack(
            '<Q', 632834208000000000 | 2 << 62)))
        self.assertEqual((632834208000000000, 2), (record.value, record.tz))

    def test_NBFX_2_2_3_12_VALUE_MAX_ENCODE(self):
        DatetimeTextRecord(3155378975999999999, 0).to_bytes()
        with self.assertRaises(WcfBinaryError):
            DatetimeTextRecord(3155378976000000000, 0).to_bytes()

    def test_NBFX_2_2_3_12_VALUE_MAX_DECODE(self):
        for value in (3155378976000000000, (1 << 62) - 1):
            with self.subTest(value=value), self.assertRaises(WcfBinaryError):
                decode(b'\x40\x01a\x96' + struct.pack('<Q', value) + b'\x01')

    def test_NBFX_2_2_3_12_TZ_RANGE_ENCODE(self):
        with self.assertRaises(WcfBinaryError):
            DatetimeTextRecord(0, 3).to_bytes()

    def test_NBFX_2_2_3_12_TZ_RANGE_DECODE(self):
        with self.assertRaises(WcfBinaryError):
            decode(b'\x40\x01a\x96' + struct.pack('<Q', 3 << 62) + b'\x01')

    def test_NBFX_2_2_3_12_FORMAT_DATE_ONLY(self):
        # documented: the time is written at midnight too (section 3, .NET)
        self.assertEqual('2006-05-17T00:00:00', str(DatetimeTextRecord(632834208000000000, 0)))

    def test_NBFX_2_2_3_12_FORMAT_SECONDS(self):
        ticks = 632834208000000000 + (13 * 3600 + 14 * 60 + 15) * 10 ** 7
        self.assertEqual('2006-05-17T13:14:15', str(DatetimeTextRecord(ticks, 0)))

    def test_NBFX_2_2_3_12_FORMAT_FRACTION(self):
        base = 632834208000000000 + 10 ** 7
        for ticks, fraction in ((5000000, '.5'), (1, '.0000001'), (1230000, '.123'),
                                (9999999, '.9999999')):
            self.assertEqual('2006-05-17T00:00:01' + fraction,
                             str(DatetimeTextRecord(base + ticks, 0)))

    def test_NBFX_2_2_3_12_FIELDS(self):
        import datetime
        self.assertEqual('0001-01-01T00:00:00', str(DatetimeTextRecord(0, 0)))
        delta = datetime.datetime(987, 2, 3, 4, 5, 6) - datetime.datetime(1, 1, 1)
        ticks = (delta.days * 86400 + delta.seconds) * 10 ** 7
        self.assertEqual('0987-02-03T04:05:06', str(DatetimeTextRecord(ticks, 0)))

    def test_NBFX_2_2_3_12_TZ_UTC(self):
        self.assertEqual('2006-05-17T00:00:00Z', str(DatetimeTextRecord(632834208000000000, 1)))

    @staticmethod
    def local_times(tz, values):
        """str() of local DateTimeText records on a host in the fixed-offset
        time zone ``tz`` (POSIX TZ: "XST-02" is +02:00)."""
        import subprocess
        import sys
        code = ('from wcf.records import DatetimeTextRecord\n'
                'for v in %r:\n'
                '    try: print(DatetimeTextRecord(v, 2))\n'
                '    except ValueError as e: print(type(e).__name__)' % (values,))
        out = subprocess.run([sys.executable, '-c', code], capture_output=True, check=True,
                             env=dict(os.environ, TZ=tz,
                                      PYTHONPATH=os.pathsep.join(__import__('sys').path)))
        return out.stdout.decode().split()

    def test_NBFX_2_2_3_12_TZ_LOCAL(self):
        # "+HH:mm" / "-HH:mm", the offset of the decoding host; documented:
        # the field holds the UTC ticks (.NET DateTime.ToBinary())
        midnight_utc = 632834208000000000
        self.assertEqual(['2006-05-17T02:00:00+02:00'], self.local_times('XST-02', [midnight_utc]))
        self.assertEqual(['2006-05-16T19:00:00-05:00'], self.local_times('XST+05', [midnight_utc]))
        self.assertEqual(['2006-05-17T05:30:00+05:30'], self.local_times('XST-05:30', [midnight_utc]))
        self.assertEqual(['2006-05-17T00:00:00+00:00'], self.local_times('UTC', [midnight_utc]))

    def test_NBFX_2_2_3_12_VALUE_MAX_LOCAL(self):
        # documented: for TZ=2 the field is DateTime.ToBinary(), a time
        # before 0001-01-01T00:00:00Z being folded below 2^62
        hour = 3600 * 10 ** 7
        self.assertEqual(['0001-01-01T01:00:00+02:00'],
                         self.local_times('XST-02', [(1 << 62) - hour]))
        with self.assertRaises(WcfBinaryError):
            DatetimeTextRecord(1 << 62, 2).to_bytes()

    def test_NBFX_2_2_3_12_TZ_UNSPECIFIED(self):
        self.assertEqual('2006-05-17T00:00:00', str(DatetimeTextRecord(632834208000000000, 0)))

    def test_NBFX_2_2_3_12_ISO8601(self):
        for ticks, tz in ((0, 0), (0, 1), (632834208000000000, 0), (632834208012345670, 1),
                          (632834208012345670, 2), (3155378975999999999, 0)):
            with self.subTest(ticks=ticks, tz=tz):
                self.assertRegex(str(DatetimeTextRecord(ticks, tz)),
                                 r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d{1,7})?'
                                 r'(Z|[+-]\d\d:\d\d)?$')


class NBFX_2_2_3_13_Chars8Text(unittest.TestCase):

    def test_NBFX_2_2_3_13_LENGTH_UINT8(self):
        self.assertEqual(b'\x98\xff' + b'a' * 255, Chars8TextRecord('a' * 255).to_bytes())
        self.assertEqual('a' * 255, content(0x98, b'\xff' + b'a' * 255))
        with self.assertRaises(WcfBinaryError):
            Chars8TextRecord('a' * 256).to_bytes()

    def test_NBFX_2_2_3_13_UTF8(self):
        self.assertEqual(b'\x98\x02\xc3\xa9', Chars8TextRecord('é').to_bytes())
        self.assertEqual('é€😀', content(0x98, b'\x09' + 'é€😀'.encode('utf-8')))

    def test_NBFX_2_2_3_13_EX(self):
        # the bytes of the example, { 0x41, 0x42, 0x43 }, are "ABC"; the
        # specification prints "abc"
        self.assertEqual('ABC', content(0x98, b'\x03\x41\x42\x43'))
        self.assertEqual('abc', content(0x98, b'\x03\x61\x62\x63'))

    def test_NBFX_2_2_3_13_FULLY_FORMED(self):
        for raw in (b'\x01\xc3', b'\x02\xe2\x82', b'\x01\xff', b'\x02\xc0\x80'):
            with self.subTest(raw=raw), self.assertRaises(WcfBinaryError):
                decode(b'\x40\x01a\x98' + raw + b'\x01')

    def test_NBFX_2_2_3_13_LOW_SURROGATE_ALONE(self):
        # a low surrogate not paired with a high one is refused
        for raw in (b'\xed\xb8\x80', b'\xed\xb8\x80\xed\xa0\xbd'):
            with self.subTest(raw=raw), self.assertRaises(WcfBinaryError):
                decode(b'\x40\x01a\x98' + bytes((len(raw),)) + raw + b'\x01')

    def test_NBFX_2_2_3_13_SURROGATE_PAIR(self):
        """Documented deviation: a pair of 3-byte surrogate sequences is
        refused, as the .NET binary reader does; the 4-byte UTF-8 form
        (RFC 3629) is the character."""
        raw = b'\xed\xa0\xbd\xed\xb8\x80'      # U+1F600 as two surrogates
        with self.assertRaises(WcfBinaryError):
            content(0x98, bytes((len(raw),)) + raw)
        raw = '\U0001F600'.encode('utf-8')
        self.assertEqual('\U0001F600', content(0x98, bytes((len(raw),)) + raw))


class NBFX_2_2_3_13_1_CharacterEscaping(unittest.TestCase):

    example = b'\x06\x22\x26\x3c\x3e\x27\x00'

    def test_NBFX_2_2_3_13_1_MINIMAL_CONTENT(self):
        self.assertEqual('"\'', content(0x98, b'\x02"\''))
        self.assertEqual('&amp;&lt;&gt;', content(0x98, b'\x03&<>'))

    def test_NBFX_2_2_3_13_1_MINIMAL_ATTRIBUTE(self):
        self.assertEqual("'", attribute_value(0x98, b"\x01'"))
        self.assertEqual('&quot;&amp;&lt;&gt;', attribute_value(0x98, b'\x04"&<>'))

    def test_NBFX_2_2_3_13_1_TABLE(self):
        self.assertNotIn('&apos;', attribute_value(0x98, b"\x01'") + content(0x98, b"\x01'"))
        self.assertEqual('&quot;', attribute_value(0x98, b'\x01"'))

    def test_NBFX_2_2_3_13_1_ILLEGAL_CHARACTERS(self):
        for char, ref in (('\x00', '&#0;'), ('\x01', '&#1;'), ('\x1f', '&#31;'),
                          ('￾', '&#65534;'), ('￿', '&#65535;')):
            raw = char.encode('utf-8')
            with self.subTest(char=char):
                self.assertEqual(ref, content(0x98, bytes((len(raw),)) + raw))
                self.assertEqual(ref, attribute_value(0x98, bytes((len(raw),)) + raw))

    def test_NBFX_2_2_3_13_1_EX_ELEMENT(self):
        self.assertEqual('"&amp;&lt;&gt;\'&#0;', content(0x98, self.example))

    def test_NBFX_2_2_3_13_1_EX_ATTRIBUTE(self):
        self.assertEqual('&quot;&amp;&lt;&gt;\'&#0;', attribute_value(0x98, self.example))

    def test_NBFX_2_2_3_13_1_WHITESPACE_REFERENCES(self):
        # documented: line ends (and tabs, line feeds in attributes) are
        # written as references, so that an XML parser keeps them
        self.assertEqual('a&#13;b\nc\td', content(0x98, b'\x07a\rb\nc\td'))
        self.assertEqual('a&#13;b&#10;c&#9;d', attribute_value(0x98, b'\x07a\rb\nc\td'))

    def test_NBFX_2_2_3_13_1_ALL_TEXT_RECORDS(self):
        with dictionary_context({1: '<&>'}):
            self.assertEqual('&lt;&amp;&gt;', content(0xAA, b'\x01'))
        self.assertEqual('&lt;&amp;', content(0xB6, b'\x04<\x00&\x00'))
        self.assertEqual('&lt; &amp;', content(0xA4, b'\x98\x01<\x98\x01&\xa6'))
        self.assertEqual('&lt;', content(0x9A, b'\x01\x00<'))
        self.assertEqual('&lt;', content(0x9C, b'\x01\x00\x00\x00<'))


class NBFX_2_2_3_14_15_Chars16Chars32Text(unittest.TestCase):

    def test_NBFX_2_2_3_14_LENGTH_UINT16(self):
        self.assertEqual(b'\x9a\xff\xff' + b'a' * 65535, Chars16TextRecord('a' * 65535).to_bytes())
        self.assertEqual('a' * 300, content(0x9A, b'\x2c\x01' + b'a' * 300))
        with self.assertRaises(WcfBinaryError):
            Chars16TextRecord('a' * 65536).to_bytes()

    def test_NBFX_2_2_3_15_LENGTH_INT32(self):
        self.assertEqual(b'\x9c\x2c\x01\x00\x00' + b'a' * 300, Chars32TextRecord('a' * 300).to_bytes())
        self.assertEqual('a' * 300, content(0x9C, b'\x2c\x01\x00\x00' + b'a' * 300))
        self.assertEqual(0x7FFFFFFF, Chars32TextRecord.max_length())

    def test_NBFX_2_2_3_15_LEN_POSITIVE(self):
        for length in (0, -1, -(1 << 31)):
            with self.subTest(length=length), self.assertRaises(WcfBinaryError):
                decode(b'\x40\x01a\x9c' + struct.pack('<i', length) + b'\x01')
        with self.assertRaises(WcfBinaryError):
            Chars32TextRecord('').to_bytes()


class NBFX_2_2_3_16_18_BytesText(unittest.TestCase):

    def test_NBFX_2_2_3_16_LENGTH_UINT8(self):
        self.assertEqual(b'\x9e\xff' + b'\x00' * 255, Bytes8TextRecord(b'\x00' * 255).to_bytes())
        with self.assertRaises(WcfBinaryError):
            Bytes8TextRecord(b'\x00' * 256).to_bytes()

    def test_NBFX_2_2_3_16_BASE64(self):
        import base64
        data = bytes(range(256))
        self.assertEqual(base64.b64encode(data[:200]).decode(),
                         content(0x9E, b'\xc8' + data[:200]))

    def test_NBFX_2_2_3_16_EX_AQID(self):
        self.assertEqual('AQID', content(0x9E, b'\x03\x01\x02\x03'))

    def test_NBFX_2_2_3_16_EX_SLASH_W(self):
        self.assertEqual('/w==', content(0x9E, b'\x01\xff'))

    def test_NBFX_2_2_3_17_LENGTH_UINT16(self):
        self.assertEqual(b'\xa0\x2c\x01' + b'\x00' * 300, Bytes16TextRecord(b'\x00' * 300).to_bytes())
        self.assertEqual('AQID', content(0xA0, b'\x03\x00\x01\x02\x03'))
        with self.assertRaises(WcfBinaryError):
            Bytes16TextRecord(b'\x00' * 65536).to_bytes()

    def test_NBFX_2_2_3_18_LENGTH_INT32(self):
        self.assertEqual(b'\xa2\x03\x00\x00\x00\x01\x02\x03', Bytes32TextRecord(b'\x01\x02\x03').to_bytes())
        self.assertEqual('AQID', content(0xA2, b'\x03\x00\x00\x00\x01\x02\x03'))

    def test_NBFX_2_2_3_18_LEN_POSITIVE(self):
        for length in (0, -1, -(1 << 31)):
            with self.subTest(length=length), self.assertRaises(WcfBinaryError):
                decode(b'\x40\x01a\xa2' + struct.pack('<i', length) + b'\x01')
        with self.assertRaises(WcfBinaryError):
            Bytes32TextRecord(b'').to_bytes()


class NBFX_2_2_3_19_ListText(unittest.TestCase):

    def test_NBFX_2_2_3_19_NO_FIELDS(self):
        self.assertEqual(b'\xa4\xa6', StartListTextRecord([]).to_bytes())
        self.assertEqual('', content(0xA4, b'\xa6'))

    def test_NBFX_2_2_3_19_SEPARATOR(self):
        self.assertEqual('1 2', content(0xA4, b'\x88\x01\x88\x02\xa6'))
        self.assertEqual('a', content(0xA4, b'\x98\x01a\xa6'))

    def test_NBFX_2_2_3_19_ITEMS_TEXT(self):
        for item in (b'\x40\x01x\x01', b'\x02\x01c', b'\x01', b'\x04\x01a\x86',
                     b'\x87', b'\x99\x01a', b'\x03'):
            with self.subTest(item=item), self.assertRaises(WcfBinaryError):
                decode(b'\x40\x01a\xa4' + item + b'\xa6\x01')
        with self.assertRaises(WcfBinaryError):
            StartListTextRecord([ShortElementRecord('x')]).to_bytes()

    def test_NBFX_2_2_3_19_NO_NESTED_LIST(self):
        with self.assertRaises(WcfBinaryError):
            decode(b'\x40\x01a\xa4\xa4\xa6\xa6\x01')
        for items in ([StartListTextRecord([])], [EndListTextRecord()]):
            with self.assertRaises(WcfBinaryError):
                StartListTextRecord(items).to_bytes()

    def test_NBFX_2_2_3_19_ENDLIST_REQUIRES_START(self):
        for wire in (b'\xa6', b'\x40\x01a\xa6\x01', b'\x40\x01a\x04\x01b\xa6\x01'):
            with self.subTest(wire=wire), self.assertRaises(WcfBinaryError):
                decode(wire)

    def test_NBFX_2_2_3_19_UNTERMINATED(self):
        for wire in (b'\x40\x01a\xa4\x86', b'\x40\x01a\xa4\x86\x01'):
            with self.subTest(wire=wire), self.assertRaises(WcfBinaryError):
                decode(wire)

    def test_NBFX_2_2_3_19_EX(self):
        self.assertEqual('true false 0 1', content(0xA4, h('86 84 80 82 A6')))
        self.assertEqual(h('A4 86 84 80 82 A6'), StartListTextRecord(
            [TrueTextRecord(), FalseTextRecord(), ZeroTextRecord(), OneTextRecord()]).to_bytes())


class NBFX_2_2_3_20_21_EmptyDictionaryText(unittest.TestCase):

    def test_NBFX_2_2_3_20_CHARS(self):
        self.assertEqual('<a b=""></a>', render(b'\x40\x01a\x04\x01b\xa8\x01'))
        self.assertEqual('<a></a>', render(b'\x40\x01a\xa9'))

    def test_NBFX_2_2_3_20_NO_FIELDS(self):
        self.assertEqual(b'\xa8', EmptyTextRecord().to_bytes())
        self.assertEqual('<a><b></b></a>', render(b'\x40\x01a\xa8\x40\x01b\x01\x01'))

    def test_NBFX_2_2_3_21_VALUE_DICTIONARYSTRING(self):
        self.assertEqual(b'\xaa\xcc\x07', DictionaryTextRecord(0x3CC).to_bytes())
        self.assertEqual('detail', content(0xAA, b'\xcc\x07'))

    def test_NBFX_2_2_3_21_EX(self):
        with dictionary_context({1: 'hello'}):
            self.assertEqual('hello', content(0xAA, b'\x01'))


class NBFX_2_2_3_22_24_UniqueIdTimeSpanUuidText(unittest.TestCase):

    raw = h('00 11 22 33 44 55 66 77 88 99 AA BB CC DD EE FF')

    def test_NBFX_2_2_3_22_LAYOUT(self):
        # Data1, Data2, Data3 little-endian, Data4 as is
        self.assertEqual(b'\xac' + self.raw, UniqueIdTextRecord('urn:uuid:' + _UUID).to_bytes())
        record = UniqueIdTextRecord.parse(io.BytesIO(self.raw))
        self.assertEqual(0x33221100, record.uuid.time_low)
        self.assertEqual(0x5544, record.uuid.time_mid)
        self.assertEqual(0x7766, record.uuid.time_hi_version)

    def test_NBFX_2_2_3_22_URN_LOWERCASE(self):
        text = content(0xAC, self.raw)
        self.assertTrue(text.startswith('urn:uuid:'))
        self.assertEqual(text.lower(), text)

    def test_NBFX_2_2_3_22_EX(self):
        self.assertEqual('urn:uuid:33221100-5544-7766-8899-aabbccddeeff', content(0xAC, self.raw))

    def test_NBFX_2_2_3_23_VALUE(self):
        self.assertEqual(b'\xae' + struct.pack('<q', -3440000000),
                         TimeSpanTextRecord(-3440000000).to_bytes())
        self.assertEqual(-3440000000, TimeSpanTextRecord.parse(
            io.BytesIO(struct.pack('<q', -3440000000))).value)

    def test_NBFX_2_2_3_23_RANGE(self):
        self.assertEqual('-P10675199DT2H48M5.4775808S', content(0xAE, struct.pack('<q', -(1 << 63))))
        self.assertEqual('P10675199DT2H48M5.4775807S', content(0xAE, struct.pack('<q', (1 << 63) - 1)))

    def test_NBFX_2_2_3_23_FORMAT(self):
        # documented: xsd:duration (section 3 examples and .NET)
        self.assertEqual('-PT5M44S', content(0xAE, h('00 C4 F5 32 FF FF FF FF')))
        self.assertEqual('PT3H20M', content(0xAE, h('00 B0 8E F0 1B 00 00 00')))
        self.assertEqual('P1DT0.5S', str(TimeSpanTextRecord(864000000000 + 5000000)))

    def test_NBFX_2_2_3_24_LAYOUT(self):
        self.assertEqual(b'\xb0' + self.raw, UuidTextRecord(_UUID).to_bytes())
        self.assertEqual(0x33221100, UuidTextRecord.parse(io.BytesIO(self.raw)).uuid.time_low)

    def test_NBFX_2_2_3_24_LOWERCASE(self):
        self.assertEqual(_UUID, content(0xB0, self.raw))

    def test_NBFX_2_2_3_24_EX(self):
        self.assertEqual('33221100-5544-7766-8899-aabbccddeeff', content(0xB0, self.raw))
        self.assertEqual('urn:uuid:' + content(0xB0, self.raw), content(0xAC, self.raw))


class NBFX_2_2_3_25_26_UInt64BoolText(unittest.TestCase):

    def test_NBFX_2_2_3_25_SIZE(self):
        self.assertEqual(b'\xb2' + struct.pack('<Q', 1337), UInt64TextRecord(1337).to_bytes())
        for value in (-1, 1 << 64):
            with self.assertRaises(WcfBinaryError):
                UInt64TextRecord(value).to_bytes()

    def test_NBFX_2_2_3_25_CHARS(self):
        self.assertEqual('0', content(0xB2, b'\x00' * 8))
        self.assertEqual('9223372036854775808', content(0xB2, struct.pack('<Q', 1 << 63)))

    def test_NBFX_2_2_3_25_EX(self):
        self.assertEqual('18446744073709551615', content(0xB2, b'\xff' * 8))

    def test_NBFX_2_2_3_26_VALUE_0_1(self):
        for value in (2, 0x80, 0xFF):
            with self.subTest(value=value), self.assertRaises(WcfBinaryError):
                decode(b'\x40\x01a\xb4' + bytes((value,)) + b'\x01')
        self.assertEqual(b'\xb4\x00', BoolTextRecord(False).to_bytes())
        self.assertEqual(b'\xb4\x01', BoolTextRecord(True).to_bytes())

    def test_NBFX_2_2_3_26_FALSE(self):
        self.assertEqual('false', content(0xB4, b'\x00'))

    def test_NBFX_2_2_3_26_TRUE(self):
        self.assertEqual('true', content(0xB4, b'\x01'))


class NBFX_2_2_3_27_30_UnicodeQNameText(unittest.TestCase):

    def test_NBFX_2_2_3_27_LENGTH(self):
        self.assertEqual(b'\xb6\x04\x3d\xd8\x00\xde', UnicodeChars8TextRecord('\U0001F600').to_bytes())
        self.assertEqual('\U0001F600', content(0xB6, b'\x04\x3d\xd8\x00\xde'))
        with self.assertRaises(WcfBinaryError):
            UnicodeChars8TextRecord('a' * 128).to_bytes()

    def test_NBFX_2_2_3_27_UTF16(self):
        for raw in (b'\x03a\x00b', b'\x02\x00\xdc'):    # odd length, lone low surrogate
            with self.subTest(raw=raw), self.assertRaises(WcfBinaryError):
                decode(b'\x40\x01a\xb6' + raw + b'\x01')

    def test_NBFX_2_2_3_27_EX(self):
        # { 0x41, 0x00, 0x42, 0x00, 0x43, 0x00 } is "ABC"; the
        # specification prints "abc"
        self.assertEqual('ABC', content(0xB6, h('06 41 00 42 00 43 00')))

    def test_NBFX_2_2_3_28_LENGTH(self):
        self.assertEqual(b'\xb8\x2c\x01' + b'a\x00' * 150, UnicodeChars16TextRecord('a' * 150).to_bytes())
        self.assertEqual('a' * 150, content(0xB8, b'\x2c\x01' + b'a\x00' * 150))
        with self.assertRaises(WcfBinaryError):
            UnicodeChars16TextRecord('a' * 32768).to_bytes()

    def test_NBFX_2_2_3_29_LENGTH(self):
        # documented: INT32, as section 3 ("BA 04 00 00 00 33 00 32 00") and
        # .NET, not the MultiByteInt31 of the text of 2.2.3.29
        self.assertEqual('32', content(0xBA, h('04 00 00 00 33 00 32 00')))
        self.assertEqual(b'\xba\x04\x00\x00\x00\x33\x00\x32\x00',
                         UnicodeChars32TextRecord('32').to_bytes())

    def test_NBFX_2_2_3_30_PREFIX_RANGE(self):
        for index in range(26):
            self.assertEqual('%s:Envelope' % chr(97 + index), content(0xBC, bytes((index, 2))))
            self.assertEqual(bytes((0xBC, index, 2)),
                             QNameDictionaryTextRecord(chr(97 + index), 2).to_bytes())
        for index in (26, 0xFF):
            with self.assertRaises(WcfBinaryError):
                decode(b'\x40\x01a\xbc' + bytes((index, 2)) + b'\x01')

    def test_NBFX_2_2_3_30_NAME_DICTIONARYSTRING(self):
        self.assertEqual('b:detail', content(0xBC, b'\x01\xcc\x07'))

    def test_NBFX_2_2_3_30_EX(self):
        with dictionary_context({1: 'name'}):
            self.assertEqual('b:name', content(0xBC, b'\x01\x01'))


class NBFX_2_2_3_31_TextWithEndElement(unittest.TestCase):

    def test_NBFX_2_2_3_31_EQUIVALENT(self):
        for t, (payload, chars) in TEXT_SAMPLES.items():
            if not Record.records[t].with_end_element:
                continue
            with self.subTest(type='0x%02X' % t):
                explicit = decode(b'\x40\x01a' + bytes((t,)) + payload + b'\x01')
                implicit = decode(b'\x40\x01a' + bytes((t + 1,)) + payload)
                self.assertEqual(render_xml(explicit), render_xml(implicit))
                self.assertEqual(type(explicit[0].childs[0]), type(implicit[0].childs[0]))

    def test_NBFX_2_2_3_31_NOT_IN_ATTRIBUTE(self):
        for t in range(0x81, 0xBE, 2):
            with self.subTest(type='0x%02X' % t), self.assertRaises(WcfBinaryError):
                decode(b'\x40\x01a\x04\x01b' + bytes((t,)) + b'\x00' * 16 + b'\x01')
        element = ShortElementRecord('a')
        element.attributes.append(ShortAttributeRecord('b', TrueTextRecord()))
        self.assertEqual(b'\x40\x01a\x04\x01b\x86\x01', dump_records([element]))

    def test_NBFX_2_2_3_31_EX(self):
        three = b'\x40' + S('value') + b'\x98' + S('123') + b'\x01'
        two = b'\x40' + S('value') + b'\x99' + S('123')
        self.assertEqual('<value>123</value>', render(three))
        self.assertEqual('<value>123</value>', render(two))
        element = ShortElementRecord('value')
        element.childs.append(Chars8TextRecord('123'))
        self.assertEqual(two, dump_records([element]))


# ---------------------------------------------------------------- MC-NBFX 2.3

class NBFX_2_3_1_EndElement(unittest.TestCase):

    def test_NBFX_2_3_1_NO_FIELDS(self):
        self.assertEqual(b'\x01', EndElementRecord().to_bytes())
        self.assertEqual('<a></a><b></b>', render(b'\x40\x01a\x01\x40\x01b\x01'))

    def test_NBFX_2_3_1_MUST_EXIST(self):
        for wire in (b'\x01', b'\x40\x01a\x01\x01', b'\x98\x01x\x01'):
            with self.subTest(wire=wire), self.assertRaises(WcfBinaryError):
                decode(wire)

    def test_NBFX_2_3_1_CLOSES_MOST_RECENT(self):
        records = decode(b'\x40\x01a\x40\x01b\x01\x40\x01c\x01\x01')
        self.assertEqual(['b', 'c'], [child.name for child in records[0].childs])
        self.assertEqual('<a><b></b><c></c></a>', render_xml(records))

    def test_NBFX_2_3_1_EX(self):
        self.assertEqual('<ENV:envelope></ENV:envelope>',
                         render(b'\x41' + S('ENV') + S('envelope') + b'\x01'))


class NBFX_2_3_2_Comment(unittest.TestCase):

    def test_NBFX_2_3_2_VALUE_STRING(self):
        self.assertEqual(b'\x02' + S('é' * 100), CommentRecord('é' * 100).to_bytes())
        self.assertEqual('é' * 100, decode(b'\x02' + S('é' * 100))[0].comment)

    def test_NBFX_2_3_2_EX(self):
        self.assertEqual('<!--comment-->', render(b'\x02' + S('comment')))

    def test_NBFX_2_3_2_RENDER(self):
        # documented: a comment XML cannot carry is refused by render_xml()
        for text in ('a--b', 'a-', 'a\x00'):
            with self.subTest(text=text), self.assertRaises(WcfBinaryError):
                render(b'\x02' + S(text))


class NBFX_2_3_3_Array(unittest.TestCase):

    def wire(self, element=b'\x40\x01a', attributes=b'', end=b'\x01', datatype=0x8D,
             count=b'\x01', data=b'\x05\x00\x00\x00'):
        return b'\x03' + element + attributes + end + bytes((datatype,)) + count + data

    def test_NBFX_2_3_3_ELEMENT(self):
        self.assertEqual('<b:a>5</b:a>', render(self.wire(element=b'\x5f\x01a')))
        for element in (b'\x98\x01a', b'\x04\x01a\x86', b'\x02\x01c', b'\x03'):
            with self.subTest(element=element), self.assertRaises(WcfBinaryError):
                decode(self.wire(element=element))

    def test_NBFX_2_3_3_ATTRIBUTES(self):
        self.assertEqual('<a xmlns="urn:x" b="1">5</a>',
                         render(self.wire(attributes=b'\x08' + S('urn:x') + b'\x04\x01b\x82')))
        for attribute in (b'\x98\x01a', b'\x40\x01x', b'\x02\x01c'):
            with self.subTest(attribute=attribute), self.assertRaises(WcfBinaryError):
                decode(self.wire(attributes=attribute))

    def test_NBFX_2_3_3_END_ELEMENT(self):
        with self.assertRaises(WcfBinaryError):
            decode(self.wire(end=b''))
        self.assertEqual(b'\x01', ArrayRecord(ShortElementRecord('a'), [Int32TextRecord(5)],
                                              []).to_bytes()[4:5])

    def test_NBFX_2_3_3_RECORDTYPE_TABLE(self):
        allowed = {0xB5, 0x8B, 0x8D, 0x8F, 0x91, 0x93, 0x95, 0x97, 0xAF, 0xB1}
        for t in range(0x100):
            if t in allowed:
                continue
            with self.subTest(type='0x%02X' % t), self.assertRaises(WcfBinaryError):
                decode(self.wire(datatype=t, data=b'\x00' * 16))
        for items in ([Int8TextRecord(1)], [UInt64TextRecord(1)], [Chars8TextRecord('a')],
                      [Int32TextRecord(1), Int16TextRecord(1)]):
            with self.subTest(items=items), self.assertRaises(WcfBinaryError):
                ArrayRecord(ShortElementRecord('a'), items, [])

    def test_NBFX_2_3_3_LENGTH_MBI31(self):
        records = decode(self.wire(count=b'\x80\x01', data=b'\x00\x00\x00\x00' * 128))
        self.assertEqual(128, len(records[0].data))
        self.assertEqual(b'\x80\x01', ArrayRecord(ShortElementRecord('a'),
                                                  [Int32TextRecord(0)] * 128, []).to_bytes()[6:8])

    def test_NBFX_2_3_3_LENGTH_NONZERO(self):
        with self.assertRaises(WcfBinaryError):
            decode(self.wire(count=b'\x00', data=b''))
        with self.assertRaises(WcfBinaryError):
            ArrayRecord(ShortElementRecord('a'), [], [])

    def test_NBFX_2_3_3_EXPANSION(self):
        wire = self.wire(attributes=b'\x04\x01b\x86', count=b'\x02',
                         data=b'\x01\x00\x00\x00\x02\x00\x00\x00')
        self.assertEqual('<a b="true">1</a><a b="true">2</a>', render(wire))
        self.assertEqual(wire, dump_records(decode(wire)))

    def test_NBFX_2_3_3_EX(self):
        wire = (b'\x03\x40' + S('item') + b'\x08' + S('http://tempuri.org') + b'\x01\x8d\x03' +
                h('01 00 00 00 02 00 00 00 03 00 00 00'))
        self.assertEqual('<item xmlns="http://tempuri.org">1</item>'
                         '<item xmlns="http://tempuri.org">2</item>'
                         '<item xmlns="http://tempuri.org">3</item>', render(wire))
        self.assertEqual(12, len(wire) - wire.index(b'\x8d\x03') - 2)


ARRAY_TYPES = [   # 2.3.3 table: record type, data size, items, characters
    (0xB5, 1, [BoolTextRecord(True), BoolTextRecord(False)], ['true', 'false']),
    (0x8B, 2, [Int16TextRecord(-2), Int16TextRecord(3)], ['-2', '3']),
    (0x8D, 4, [Int32TextRecord(-2), Int32TextRecord(3)], ['-2', '3']),
    (0x8F, 8, [Int64TextRecord(-2), Int64TextRecord(1 << 40)], ['-2', '1099511627776']),
    (0x91, 4, [FloatTextRecord(1.5), FloatTextRecord(-0.25)], ['1.5', '-0.25']),
    (0x93, 8, [DoubleTextRecord(1.5), DoubleTextRecord(-0.25)], ['1.5', '-0.25']),
    (0x95, 16, [DecimalTextRecord(Decimal(False, 0, 15, 1)),
                DecimalTextRecord(Decimal(True, 0, 2, 0))], ['1.5', '-2']),
    (0x97, 8, [DatetimeTextRecord(632834208000000000, 1),
               DatetimeTextRecord(632834208000000000, 0)],
     ['2006-05-17T00:00:00Z', '2006-05-17T00:00:00']),
    (0xAF, 8, [TimeSpanTextRecord(36000000000), TimeSpanTextRecord(-10000000)],
     ['PT1H', '-PT1S']),
    (0xB1, 16, [UuidTextRecord(_UUID), UuidTextRecord(int=1)],
     [_UUID, '00000000-0000-0000-0000-000000000001']),
]


def _array_type_test(t, size, items, chars):
    def test(self):
        wire = ArrayRecord(ShortElementRecord('a'), items, []).to_bytes()
        self.assertEqual(h('03 40 01 61 01') + bytes((t, len(items))), wire[:7])
        self.assertEqual(7 + size * len(items), len(wire))
        self.assertEqual(''.join('<a>%s</a>' % c for c in chars), render(wire))
        self.assertEqual(wire, dump_records(decode(wire)))
        with self.assertRaises(WcfBinaryError):          # Data shorter than Length x size
            decode(wire[:-1])
    test.__doc__ = 'MC-NBFX 2.3.3: Array of 0x%02X, %d bytes per item' % (t, size)
    return test


for _t, _size, _items, _chars in ARRAY_TYPES:
    setattr(NBFX_2_3_3_Array, 'test_NBFX_2_3_3_TYPE_%02X' % _t,
            _array_type_test(_t, _size, _items, _chars))


# ---------------------------------------------------------------- MC-NBFX 3

class NBFX_3_StructureExamples(unittest.TestCase):
    """Every row of the table of section 3: decoded, rendered as the
    "Characters represented" column, and encoded again byte for byte."""

    def check_row(self, name, record_type, wire, chars):
        data = h(wire)
        with strn_dictionary():
            records = decode(data)
            self.assertIn(record_type, record_types(records))
            self.assertEqual(chars, render_xml(records))
            self.assertEqual(data, dump_records(records))


def _example_test(row):
    def test(self):
        self.check_row(*row)
    test.__doc__ = 'MC-NBFX section 3: %s (0x%02X)' % row[:2]
    return test


for _row in SECTION3:
    setattr(NBFX_3_StructureExamples, 'test_NBFX_3_EX_' + _row[0], _example_test(_row))


# ---------------------------------------------------------------- MC-NBFX 4

class _ReadSpy(io.BytesIO):
    """A file whose read() records the largest size requested."""
    largest = 0

    def read(self, size=-1):
        self.largest = max(self.largest, size)
        return super().read(size)


class NBFX_4_SecurityConsiderations(unittest.TestCase):

    def test_NBFX_4_SAME_THREATS(self):
        from wcf.records import Quotas
        with self.assertRaises(WcfBinaryError):              # entity expansion
            XMLParser.parse('<!DOCTYPE a [<!ENTITY e "x">]><a>&e;</a>')
        with self.assertRaises(WcfBinaryError):              # nesting
            Record.parse(io.BytesIO(b'\x40\x01a' * 65 + b'\x01' * 65))
        with self.assertRaises(WcfBinaryError):              # markup injection
            render(b'\x40' + S('a b="c"') + b'\x01')
        with self.assertRaises(WcfBinaryError):              # amplification
            Record.parse(io.BytesIO(b'\x40\x01a' + b'\xaa\x48' * 4000 + b'\x01'),
                         Quotas(max_chars=100000))

    def test_NBFX_4_ALLOC_ARRAY(self):
        wire = b'\x03\x40\x01a\x01\x8f' + MultiByteInt31(1 << 30).to_bytes() + b'\x00' * 8
        fp = io.BytesIO(wire)
        with self.assertRaises(WcfBinaryError):
            Record.parse(fp)
        self.assertEqual(len(wire) - 8, fp.tell())   # refused before any item

    def test_NBFX_4_ALLOC_LIST(self):
        from wcf.records import Quotas
        with self.assertRaises(WcfBinaryError):
            Record.parse(io.BytesIO(b'\x40\x01a\xa4' + b'\x80' * 1000 + b'\xa6\x01'),
                         Quotas(max_records=100))

    def test_NBFX_4_ALLOC_LENGTH_FIELDS(self):
        for wire in (b'\x40\x01a\x9c\xff\xff\xff\x7f',          # Chars32Text
                     b'\x40\x01a\xa2\xff\xff\xff\x7f',          # Bytes32Text
                     b'\x40\x01a\xba\xff\xff\xff\x7f',          # UnicodeChars32Text
                     b'\x40\xff\xff\xff\xff\x07',               # String
                     b'\x02\xff\xff\xff\xff\x07'):              # Comment
            with self.subTest(wire=wire):
                fp = _ReadSpy(wire)
                with self.assertRaises(WcfBinaryError):
                    Record.parse(fp)
                self.assertLessEqual(fp.largest, 1 << 20)


# ------------------------------------------------------------------ MC-NBFS

# MC-NBFS 2.1: SHA-256 of "value=characters" lines (decimal value, sorted),
# computed from the table of the specification (487 entries, 0x00 to 0x3CC,
# 0xA2 being the empty string)
NBFS_TABLE_SHA256 = '5e8c12953753e29565d3f8c0dcaf03e6421963912d6fb7d4a96bb9cf17537f2c'

NBFS_EXAMPLE = h('56 02 0B 01 61 06 0B 01 73 04 56 08 44 0A 1E 00 '
                 '82 99 06 61 63 74 69 6F 6E 01 56 0E 40 09 49 6E '
                 '76 65 6E 74 6F 72 79 81 01 01')
NBFS_EXAMPLE_XML = (
    '<s:Envelope xmlns:a="http://www.w3.org/2005/08/addressing" '
    'xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Header>'
    '<a:Action s:mustUnderstand="1">action</a:Action></s:Header><s:Body>'
    '<Inventory>0</Inventory></s:Body></s:Envelope>')


class NBFS_2_Structures(unittest.TestCase):

    def test_NBFS_2_IDENTICAL(self):
        # an MC-NBFS document is an MC-NBFX document: same records, same codec
        self.assertEqual(NBFS_EXAMPLE, dump_records(Record.parse(io.BytesIO(NBFS_EXAMPLE))))


class NBFS_2_1_DictionaryString(unittest.TestCase):

    def test_NBFS_2_1_EVEN(self):
        self.assertTrue(all(key % 2 == 0 for key in static_dictionary))
        for wire in (b'\x42\x01\x01', b'\x40\x01a\xab\x01', b'\x40\x01a\x06\x01\x86\x01'):
            with self.subTest(wire=wire), self.assertRaises(WcfBinaryError):
                decode(wire)
        for make in (lambda: DictionaryTextRecord(1).to_bytes(),
                     lambda: ShortDictionaryElementRecord(3)):
            with self.assertRaises(WcfBinaryError):
                make()

    def test_NBFS_2_1_MBI31(self):
        self.assertEqual(b'\x42\xcc\x07', ShortDictionaryElementRecord(0x3CC).to_bytes())
        self.assertEqual('<detail></detail>', render(b'\x42\xcc\x07\x01'))

    def test_NBFS_2_1_TABLE_VALUES(self):
        for index in (0x3CE, 0x3D0, 0x1000, 0x7FFFFFFE):
            raw = MultiByteInt31(index).to_bytes()
            with self.subTest(index=index):
                with self.assertRaises(WcfBinaryError):
                    decode(b'\x40\x01a\xab' + raw)
                with self.assertRaises(WcfBinaryError):
                    DictionaryTextRecord(index).to_bytes()

    def test_NBFS_2_1_TABLE_CHARACTERS(self):
        self.assertEqual(487, len(static_dictionary))
        self.assertEqual(set(range(0, 0x3CE, 2)), set(static_dictionary))
        blob = '\n'.join('%d=%s' % (k, static_dictionary[k])
                         for k in sorted(static_dictionary)).encode('utf-8')
        self.assertEqual(NBFS_TABLE_SHA256, hashlib.sha256(blob).hexdigest())
        for index, chars in ((0x00, 'mustUnderstand'), (0x02, 'Envelope'),
                             (0x04, 'http://www.w3.org/2003/05/soap-envelope'),
                             (0x06, 'http://www.w3.org/2005/08/addressing'),
                             (0xA0, 'qname'), (0xA4, 'From'), (0x3C2,
                              'http://schemas.xmlsoap.org/soap/envelope/'),
                             (0x3CC, 'detail')):
            self.assertEqual(chars, static_dictionary[index])

    def test_NBFS_2_1_EMPTY_0xA2(self):
        self.assertEqual('', static_dictionary[0xA2])
        self.assertEqual('<a b=""></a>', render(b'\x40\x01a\x04\x01b\xaa\xa2\x01\x01'))
        with self.assertRaises(WcfBinaryError):
            decode(b'\x42\xa2\x01\x01')


NBFS_ROWS = [  # MC-NBFS section 3: (string to encode, record, *WithEndElement, bytes)
    ('<s:Envelope', lambda: PREFIX_DICTIONARY_ELEMENTS['s'](2), False, '56 02'),
    ('xmlns:a="http://www.w3.org/2005/08/addressing"',
     lambda: DictionaryXmlnsAttributeRecord('a', 6), False, '0B 01 61 06'),
    ('xmlns:s="http://www.w3.org/2003/05/soap-envelope"',
     lambda: DictionaryXmlnsAttributeRecord('s', 4), False, '0B 01 73 04'),
    ('<s:Header', lambda: PREFIX_DICTIONARY_ELEMENTS['s'](8), False, '56 08'),
    ('<a:Action', lambda: PREFIX_DICTIONARY_ELEMENTS['a'](10), False, '44 0A'),
    ('s:mustUnderstand="1"',
     lambda: PREFIX_DICTIONARY_ATTRIBUTES['s'](0, OneTextRecord()), False, '1E 00 82'),
    ('action', lambda: Chars8TextRecord('action'), True, '99 06 61 63 74 69 6F 6E'),
    ('</s:Header>', EndElementRecord, False, '01'),
    ('<s:Body', lambda: PREFIX_DICTIONARY_ELEMENTS['s'](14), False, '56 0E'),
    ('<Inventory', lambda: ShortElementRecord('Inventory'), False,
     '40 09 49 6E 76 65 6E 74 6F 72 79'),
    ('0', ZeroTextRecord, True, '81'),
    ('</s:Body>', EndElementRecord, False, '01'),
    ('</s:Envelope>', EndElementRecord, False, '01'),
]


class NBFS_3_StructureExamples(unittest.TestCase):

    def test_NBFS_3_EX_DOCUMENT(self):
        records = Record.parse(io.BytesIO(NBFS_EXAMPLE))
        self.assertEqual(NBFS_EXAMPLE_XML, render_xml(records))
        self.assertEqual(NBFS_EXAMPLE, dump_records(records))

    def test_NBFS_3_EX_ROWS(self):
        stream = b''
        for chars, make, with_end_element, raw in NBFS_ROWS:
            record = make()
            encoded = record.to_bytes()
            if with_end_element:     # "action</a:Action>", "0</Inventory>"
                encoded = bytes((encoded[0] + 1,)) + encoded[1:]
            with self.subTest(row=chars):
                self.assertEqual(h(raw), encoded)
                if chars.startswith('<') and not chars.startswith('</'):
                    self.assertEqual(chars + '>', str(record))
                elif not chars.startswith('<'):
                    self.assertEqual(chars, str(record))
            stream += h(raw)
        self.assertEqual(NBFS_EXAMPLE, stream)

    def test_NBFS_3_EX_FROM_XML(self):
        # documented: XML values are lexical text by default, so "1" and "0"
        # are Chars8Text, not OneText and ZeroTextWithEndElement; every other
        # record is the one of the example
        wire = dump_records(XMLParser.parse(NBFS_EXAMPLE_XML))
        self.assertEqual(NBFS_EXAMPLE.replace(b'\x82', b'\x98\x01\x31')
                         .replace(b'\x81\x01\x01', b'\x99\x01\x30\x01\x01'), wire)
        self.assertEqual(NBFS_EXAMPLE_XML, render(wire))
        records = XMLParser.parse(NBFS_EXAMPLE_XML,
                                  type_overrides={'/{http://www.w3.org/2003/05/soap-envelope}'
                                                  'Envelope/{http://www.w3.org/2003/05/'
                                                  'soap-envelope}Body/Inventory': 'int8'})
        self.assertIn(b'\x89\x00', dump_records(records))


# ----------------------------------------------------------------- MC-NBFSE

NBFSE_TABLE = h('11 06 61 63 74 69 6F 6E 09 49 6E 76 65 6E 74 6F 72 79')
NBFSE_EXAMPLE = NBFSE_TABLE + h('56 02 0B 01 61 06 0B 01 73 04 56 08 44 0A 1E 00 '
                                '82 AB 01 01 56 0E 42 03 81 01 01')


class NBFSE_2_Structures(unittest.TestCase):

    def test_NBFSE_2_STRUCTURES_IDENTICAL(self):
        # after its StringTable, an MC-NBFSE document is an MC-NBFS document
        document = BinaryXmlSession().parse_document(b'\x00' + NBFS_EXAMPLE)
        self.assertEqual(NBFS_EXAMPLE_XML, document.render_xml())
        self.assertEqual(b'\x00' + NBFS_EXAMPLE, document.to_bytes())

    def test_NBFSE_2_PRECEDED_BY_STRINGTABLE(self):
        with self.assertRaises(WcfBinaryError):
            BinaryXmlSession().parse_document(b'')
        wire = BinaryXmlSession().encode_xml('<z/>')
        self.assertEqual(b'\x00\x40\x01z\x01', wire)
        document = BinaryXmlSession().parse_document(b'\x00\x40\x01a\x01')
        self.assertEqual('<a></a>', document.render_xml())


class NBFSE_2_1_StringTable(unittest.TestCase):

    def test_NBFSE_2_1_SIZE_MBI31(self):
        self.assertEqual(b'\x82\x01\x80\x01' + b'x' * 128, encode_string_table(['x' * 128]))
        session = BinaryXmlSession()
        session.parse_document(encode_string_table(['x' * 128]) + b'\x42\x01\x01')
        self.assertEqual({1: 'x' * 128}, session.dictionary)

    def test_NBFSE_2_1_SIZE_BYTES(self):
        self.assertEqual(b'\x08\x02\xc3\xa9\x04long', encode_string_table(['é', 'long']))

    def test_NBFSE_2_1_FIT_EXACTLY(self):
        for wire in (b'\x02\x05abcde\x40\x01a\x01',    # a String longer than Size
                     b'\x01\x80\x40\x01a\x01',          # a truncated length
                     b'\x05\x01a'):                     # Size beyond the document
            with self.subTest(wire=wire), self.assertRaises(WcfBinaryError):
                BinaryXmlSession().parse_document(wire)

    def test_NBFSE_2_1_UNIQUE_DECODE(self):
        with self.assertRaises(WcfBinaryError):
            BinaryXmlSession().parse_document(encode_string_table(['a', 'a']) + b'\x40\x01x\x01')

    def test_NBFSE_2_1_UNIQUE_ENCODE(self):
        session = BinaryXmlSession()
        with self.assertRaises(WcfBinaryError):
            session.encode_xml('<x/>', new_strings=['a', 'a'])
        self.assertEqual({}, session.dictionary)

    def test_NBFSE_2_1_NOT_IN_PRIOR_DECODE(self):
        session = BinaryXmlSession()
        session.parse_document(encode_string_table(['a']) + b'\x40\x01x\x01')
        with self.assertRaises(WcfBinaryError):
            session.parse_document(encode_string_table(['a']) + b'\x40\x01x\x01')

    def test_NBFSE_2_1_NOT_IN_PRIOR_ENCODE(self):
        session = BinaryXmlSession()
        session.encode_xml('<x/>', new_strings=['a'])
        with self.assertRaises(WcfBinaryError):
            session.encode_xml('<x/>', new_strings=['a'])

    def test_NBFSE_2_1_ID_1(self):
        session = BinaryXmlSession()
        session.parse_document(encode_string_table(['first']) + b'\x42\x01\x01')
        self.assertEqual({1: 'first'}, session.dictionary)
        session.reset()
        session.encode_xml('<x/>', new_strings=['again'])
        self.assertEqual({1: 'again'}, session.dictionary)

    def test_NBFSE_2_1_NEXT_ODD(self):
        session = BinaryXmlSession()
        session.parse_document(encode_string_table(['a', 'b']) + b'\x42\x03\x01')
        session.parse_document(encode_string_table(['c']) + b'\x42\x05\x01')
        self.assertEqual({1: 'a', 3: 'b', 5: 'c'}, session.dictionary)

    def test_NBFSE_2_1_MAINTAIN(self):
        session = BinaryXmlSession()
        session.parse_document(encode_string_table(['a']) + b'\x42\x01\x01')
        for _ in range(3):
            self.assertEqual('<a></a>', session.parse_document(b'\x00\x42\x01\x01').render_xml())


class NBFSE_2_2_DictionaryString(unittest.TestCase):

    def test_NBFSE_2_2_EVEN(self):
        session = BinaryXmlSession()
        document = session.parse_document(encode_string_table(['Header']) + b'\x42\x02\x42\x01\x01\x01')
        self.assertEqual('<Envelope><Header></Header></Envelope>', document.render_xml())

    def test_NBFSE_2_2_ODD_PROCESSED(self):
        for wire in (b'\x00\x42\x01\x01', encode_string_table(['a']) + b'\x42\x03\x01'):
            with self.subTest(wire=wire), self.assertRaises(WcfBinaryError):
                BinaryXmlSession().parse_document(wire)

    def test_NBFSE_2_2_ODD_CHARACTERS(self):
        document = BinaryXmlSession().parse_document(
            encode_string_table(['a<b']) + b'\x40\x01x\xab\x01')
        self.assertEqual('<x>a&lt;b</x>', document.render_xml())


class NBFSE_3_StructureExamples(unittest.TestCase):

    def test_NBFSE_3_EX_VERBOSE_RECORDS(self):
        self.assertEqual('<a>action</a>', render(b'\x40\x01a' + h('99 06 61 63 74 69 6F 6E')))
        self.assertEqual('<Inventory></Inventory>', render(h('40 09 49 6E 76 65 6E 74 6F 72 79 01')))

    def test_NBFSE_3_EX_STRINGTABLE(self):
        self.assertEqual(NBFSE_TABLE, encode_string_table(['action', 'Inventory']))

    def test_NBFSE_3_EX_IDS(self):
        session = BinaryXmlSession()
        session.parse_document(NBFSE_EXAMPLE)
        self.assertEqual({1: 'action', 3: 'Inventory'}, session.dictionary)

    def test_NBFSE_3_EX_DOCUMENT(self):
        document = BinaryXmlSession().parse_document(NBFSE_EXAMPLE)
        self.assertEqual(NBFS_EXAMPLE_XML, document.render_xml())
        self.assertEqual(NBFSE_EXAMPLE, document.to_bytes())

    def test_NBFSE_3_EX_AB01(self):
        with dictionary_context({1: 'action'}):
            self.assertEqual('<a>action</a>', render(b'\x40\x01a\xab\x01'))
            element = ShortElementRecord('a')
            element.childs.append(DictionaryTextRecord(1))
            self.assertEqual(b'\x40\x01a\xab\x01', dump_records([element]))

    def test_NBFSE_3_EX_4203(self):
        with dictionary_context({1: 'action', 3: 'Inventory'}):
            self.assertEqual(b'\x42\x03', ShortDictionaryElementRecord(3).to_bytes())
            self.assertEqual('<Inventory></Inventory>', render(b'\x42\x03\x01'))

    def test_NBFSE_3_EX_ENCODE(self):
        wire = BinaryXmlSession().encode_xml(NBFS_EXAMPLE_XML,
                                             new_strings=['action', 'Inventory'])
        self.assertTrue(wire.startswith(NBFSE_TABLE))
        self.assertIn(b'\xab\x01\x01', wire)
        self.assertIn(b'\x42\x03', wire)
        self.assertEqual(NBFS_EXAMPLE_XML, BinaryXmlSession().parse_document(wire).render_xml())


class NBFSE_4_SecurityConsiderations(unittest.TestCase):

    def test_NBFSE_4_LIMIT_STRINGTABLE(self):
        session = BinaryXmlSession(max_table_bytes=10, max_strings=2, max_session_bytes=12)
        for wire in (encode_string_table(['x' * 20]) + b'\x40\x01a\x01',
                     encode_string_table(['a', 'b', 'c']) + b'\x40\x01a\x01'):
            with self.subTest(wire=wire[:4]), self.assertRaises(WcfBinaryError):
                session.parse_document(wire)
        session.parse_document(encode_string_table(['x' * 8]) + b'\x40\x01a\x01')
        with self.assertRaises(WcfBinaryError):
            session.parse_document(encode_string_table(['y' * 8]) + b'\x40\x01a\x01')

    def test_NBFSE_4_AMPLIFICATION(self):
        wire = encode_string_table(['x' * 60000]) + b'\x40\x01a' + b'\xaa\x01' * 300 + b'\x01'
        with self.assertRaises(WcfBinaryError):
            BinaryXmlSession().parse_document(wire)


if __name__ == '__main__':
    unittest.main()
