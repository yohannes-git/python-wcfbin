"""Independent regression cases for python-wcfbin (against Microsoft MC-NBFX).

Run in the extracted project root:
    PYTHONPATH=. python -m unittest -v /path/to/test_microsoft_independent.py

These were originally failing independent-audit cases and are now permanent
regression checks for the corresponding conformity fixes.
"""
import io
import unittest

from wcf.records import Record, render_xml
from wcf.records.text import FloatTextRecord, DoubleTextRecord, DatetimeTextRecord, TimeSpanTextRecord
from wcf.xml2records import XMLParser
from wcf.session import BinaryXmlSession


def parse_wire(hexdump):
    return Record.parse(io.BytesIO(bytes.fromhex(hexdump)))


class IndependentMicrosoftNbfxTests(unittest.TestCase):
    def test_session_dynamic_dictionary_against_microsoft_soap_example(self):
        # [MC-NBFSE] section 3; actions and inventory entries are IDs 1 and 3.
        wire = bytes.fromhex('11 06 61 63 74 69 6F 6E 09 49 6E 76 65 6E 74 6F 72 79 '
                             '56 02 0B 01 61 06 0B 01 73 04 56 08 44 0A 1E 00 82 AB 01 01 '
                             '56 0E 42 03 81 01 01')
        message = BinaryXmlSession().parse_document(wire)
        self.assertEqual(wire, message.to_bytes())
        self.assertIn('action</a:Action>', message.render_xml())
        self.assertIn('<Inventory>0</Inventory>', message.render_xml())

    def test_xml_lexical_version_remains_string(self):
        wire = BinaryXmlSession().encode_xml('<version>8.0</version>')
        self.assertIn(b'8.0', wire)
        self.assertEqual('<version>8.0</version>', BinaryXmlSession().parse_document(wire).render_xml())

    def test_datetime_midnight_as_in_normative_section_22312(self):
        self.assertEqual('2006-05-17', str(DatetimeTextRecord(632834208000000000, 0)))

    def test_timespan_no_days_as_in_normative_section_22323(self):
        self.assertEqual('00:05:44', str(TimeSpanTextRecord(3440000000)))

    def test_float_text_is_shortest_32bit_decimal_microsoft_example_1(self):
        self.assertEqual('<doc a="1.1"></doc>', render_xml(parse_wire(
            '40 03 64 6F 63 04 01 61 90 CD CC 8C 3F 01')))

    def test_float_text_is_shortest_32bit_decimal_microsoft_example_2(self):
        self.assertEqual('<Price>32.45</Price>', render_xml(parse_wire(
            '40 05 50 72 69 63 65 91 CD CC 01 42')))

    def test_double_text_exponential_uses_uppercase_e(self):
        self.assertNotIn('e', str(DoubleTextRecord(1e-7)))

    def test_double_text_exponential_not_fixed_integer(self):
        self.assertEqual('1E+20', str(DoubleTextRecord(1e20)))

    def test_attribute_value_must_be_text_record(self):
        # [MC-NBFX] section 2.2.2.1: Value is a text record, not an Element.
        with self.assertRaises(ValueError):
            parse_wire('40 01 72 04 01 61 40 01 78 01')

    def test_attribute_name_must_be_nonempty(self):
        with self.assertRaises(ValueError):
            parse_wire('40 01 72 04 00 86 01')

    def test_attribute_name_must_not_be_xmlns(self):
        with self.assertRaises(ValueError):
            parse_wire('40 01 72 04 05 78 6D 6C 6E 73 86 01')

    def test_element_name_must_be_nonempty(self):
        with self.assertRaises(ValueError):
            parse_wire('40 00 01')

    def test_chars32_length_must_be_positive(self):
        with self.assertRaises(ValueError):
            parse_wire('40 01 72 9D 00 00 00 00')

    def test_bytes32_length_must_be_positive(self):
        with self.assertRaises(ValueError):
            parse_wire('40 01 72 A3 00 00 00 00')


if __name__ == '__main__':
    unittest.main()
