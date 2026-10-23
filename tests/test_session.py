"""MC-NBFSE 2.1/2.2 tests: independent wire vectors and state rules."""

import io
import unittest
from concurrent.futures import ThreadPoolExecutor
from xml.etree import ElementTree as ET

from wcf.datatypes import MultiByteInt31, Utf8String
from wcf.dictionary import dictionary, inverted_dict
from wcf.records import Record, dump_records, render_xml
from wcf.session import BinaryXmlSession, encode_string_table


class NbfseTests(unittest.TestCase):
    def test_string_table_known_bytes(self):
        self.assertEqual(b'\x08\x02\xc3\xa9\x04long', encode_string_table(['é', 'long']))
        self.assertEqual(b'\x00', encode_string_table(()))
        self.assertEqual(b'\x82\x01\x80\x01' + b'x'*128,
                         encode_string_table(['x' * 128]))

    def test_microsoft_wire_layout_and_session_indices(self):
        # Table: 'widget' -> id 1, 'urn:demo' -> id 3.
        # NBFX: <widget xmlns="urn:demo">8.0</widget>.
        doc = (b'\x10\x06widget\x08urn:demo'
               b'\x42\x01\x0a\x03\x98\x038.0\x01')
        session = BinaryXmlSession()
        parsed = session.parse_document(doc)
        self.assertEqual(doc, parsed.to_bytes())
        self.assertEqual('<widget xmlns="urn:demo">8.0</widget>', parsed.render_xml())
        self.assertEqual({1: 'widget', 3: 'urn:demo'}, session.dictionary)
        second = b'\x00\x42\x01\x99\x011'
        decoded = session.parse_document(second)
        self.assertEqual('<widget>1</widget>', decoded.render_xml())
        self.assertEqual(second, decoded.to_bytes())
        # A standalone MC-NBFX parser MUST reject session dictionary IDs.
        with self.assertRaises(KeyError):
            Record.parse(io.BytesIO(second[1:]))

    def test_microsoft_official_soap_example_with_string_table(self):
        # MC-NBFS section 3 + MC-NBFSE section 3: "action" is ID 1,
        # "Inventory" is ID 3. Other SOAP names come from MC-NBFS (even IDs).
        # WCF SOAP bytes are from the official example with precisely the two
        # documented replacements (AB 01 and 42 03).
        wire = (encode_string_table(['action', 'Inventory']) + bytes.fromhex(
            '56 02 0B 01 61 06 0B 01 73 04 '
            '56 08 44 0A 1E 00 82 AB 01 01 '
            '56 0E 42 03 81 01 01'))
        document = BinaryXmlSession().parse_document(wire)
        self.assertEqual(wire, document.to_bytes())
        root = ET.fromstring(document.render_xml())
        ns_soap = '{http://www.w3.org/2003/05/soap-envelope}'
        ns_addr = '{http://www.w3.org/2005/08/addressing}'
        self.assertEqual(ns_soap + 'Envelope', root.tag)
        action = root.find(ns_soap + 'Header/' + ns_addr + 'Action')
        self.assertEqual('action', action.text)
        self.assertEqual('1', action.attrib[ns_soap + 'mustUnderstand'])
        inventory = root.find(ns_soap + 'Body/Inventory')
        self.assertEqual('0', inventory.text)

    def test_strings_in_session_tables_are_reused_as_text(self):
        sender = BinaryXmlSession()
        receiver = BinaryXmlSession()
        first = sender.encode_xml('<myCustomRoot>8.0</myCustomRoot>', new_strings=['myCustomRoot', '8.0'])
        # StringTable [myCustomRoot -> 1, 8.0 -> 3], ShortDictionaryElement (42),
        # DictionaryTextWithEndElement (AB), both with odd dictionary IDs.
        self.assertTrue(first.endswith(b'\x42\x01\xab\x03'))
        self.assertEqual('<myCustomRoot>8.0</myCustomRoot>', receiver.parse_document(first).render_xml())
        second = sender.encode_xml('<myCustomRoot value="8.0">8.0</myCustomRoot>')
        self.assertEqual('<myCustomRoot value="8.0">8.0</myCustomRoot>',
                         receiver.parse_document(second).render_xml())
        self.assertTrue(second.startswith(b'\x00'))
        # A schema override wins over DictionaryText: no accidental typing.
        third = sender.encode_xml('<myCustomRoot>8.0</myCustomRoot>', type_overrides={'/myCustomRoot': 'double'})
        self.assertEqual('<myCustomRoot>8</myCustomRoot>', receiver.parse_document(third).render_xml())
        self.assertIn(b'\x93', third)

    def test_encode_dynamic_and_preserve_lexical_version(self):
        outgoing = BinaryXmlSession()
        incoming = BinaryXmlSession()
        data = outgoing.encode_xml('<customRoot xmlns="urn:app"><version>8.0</version></customRoot>',
                                   new_strings=['customRoot', 'urn:app', 'version'])
        self.assertEqual(b'\x42\x01', data[len(encode_string_table(['customRoot', 'urn:app', 'version'])):
                                           len(encode_string_table(['customRoot', 'urn:app', 'version'])) + 2])
        decoded = incoming.parse_document(data)
        self.assertEqual('<customRoot xmlns="urn:app"><version>8.0</version></customRoot>', decoded.render_xml())
        self.assertEqual(data, decoded.to_bytes())
        later = outgoing.encode_xml('<customRoot><version>9.0</version></customRoot>')
        self.assertEqual(0, later[0])  # empty per-document StringTable
        self.assertEqual('<customRoot><version>9.0</version></customRoot>', incoming.parse_document(later).render_xml())
        self.assertEqual(3, len(incoming.dictionary))

    def test_even_static_dictionary_works_alongside_odd(self):
        sess = BinaryXmlSession()
        doc = sess.encode_xml('<Envelope><hello>yes</hello></Envelope>', ['hello'])
        # static Envelope -> even id 2; hello -> odd id 1
        parsed = sess.parse_document(b'\x00' + doc[len(encode_string_table(['hello'])):])
        self.assertEqual('<Envelope><hello>yes</hello></Envelope>', parsed.render_xml())

    def test_duplicate_within_table_and_previous_table_rejected(self):
        sess = BinaryXmlSession()
        bad_table = encode_string_table(['a', 'a']) + b'\x40\x01x\x01'
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            sess.parse_document(bad_table)
        self.assertEqual({}, sess.dictionary)
        sess.parse_document(encode_string_table(['a']) + b'\x40\x01a\x01')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            sess.parse_document(encode_string_table(['a']) + b'\x40\x01b\x01')
        self.assertEqual({1: 'a'}, sess.dictionary)

    def test_truncated_or_invalid_table_and_unknown_ids_rejected(self):
        invalid = [b'', b'\x80', b'\x09\x01a', b'\x01\x80', b'\x01\xff',
                   b'\x02\x01a\x00', b'\x00\x42\x01\x01',
                   b'\x00\x40\x01x\xaa\x01\x01']
        for data in invalid:
            with self.subTest(data=data), self.assertRaises((ValueError, KeyError, UnicodeError)):
                BinaryXmlSession().parse_document(data)

    def test_atomic_rollback_for_bad_xml_and_bad_encoding(self):
        s = BinaryXmlSession()
        with self.assertRaises(ValueError):
            s.parse_document(encode_string_table(['good']) + b'\x40\x01r')
        self.assertEqual({}, s.dictionary)
        with self.assertRaises(Exception):
            s.encode_xml('<unclosed>', new_strings=['good'])
        self.assertEqual({}, s.dictionary)

    def test_limits_and_reset(self):
        s = BinaryXmlSession(max_table_bytes=5, max_document_bytes=500)
        with self.assertRaisesRegex(ValueError, 'size limit'):
            s.parse_document(encode_string_table(['too long']) + b'\x40\x01x\x01')
        with self.assertRaisesRegex(ValueError, 'size limit'):
            s.encode_xml('<ok/>', new_strings=['too long'])
        s.encode_xml('<ok/>', new_strings=['ok'])
        self.assertEqual({1: 'ok'}, s.dictionary)
        s.reset()
        self.assertEqual({}, s.dictionary)
        with self.assertRaises(KeyError):
            s.parse_document(b'\x00\x42\x01\x01')

    def test_context_scoping_and_snapshot_outliving_session(self):
        s = BinaryXmlSession()
        doc = s.parse_document(encode_string_table(['alpha']) + b'\x42\x01\x01')
        self.assertEqual('<alpha></alpha>', doc.render_xml())
        s.reset()
        self.assertEqual('<alpha></alpha>', doc.render_xml())
        self.assertEqual(encode_string_table(['alpha']) + b'\x42\x01\x01', doc.to_bytes())
        self.assertNotIn(1, dictionary)
        self.assertNotIn('alpha', inverted_dict)

    def test_separate_connections_are_isolated(self):
        def parse_one(s):
            session = BinaryXmlSession()
            return session.parse_document(encode_string_table([s]) + b'\x42\x01\x01').render_xml()
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(['<alpha></alpha>', '<beta></beta>'],
                             list(pool.map(parse_one, ['alpha', 'beta'])))

    def test_qname_and_dictionary_attribute_use_odd_ids(self):
        session = BinaryXmlSession()
        # <r myattr="s" xmlns:p="urn:x">p:n</customRoot>
        table = encode_string_table(['myattr', 'urn:x', 'n'])
        wire = (table + b'\x40\x01r\x06\x01\x98\x01s\x0b\x01p\x03'
                b'\xbc\x0f\x05\x01')
        # QName b0 prefix=15 ('p'), DictionaryString 5 ('n')
        document = session.parse_document(wire)
        self.assertEqual(wire, document.to_bytes())
        self.assertEqual('<r myattr="s" xmlns:p="urn:x">p:n</r>', document.render_xml())
        ET.fromstring(document.render_xml())


if __name__ == '__main__':
    unittest.main()
