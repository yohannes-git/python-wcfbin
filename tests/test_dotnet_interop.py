"""Messages produced by the WCF binary message encoder of .NET Framework
4.8.1 (tests/dotnet/run.ps1): the library reads what .NET reads, and its
own encodings read back the same.

The python to .NET direction needs Windows: run tests/dotnet/run.ps1
-Mode consume on the encodings of this library (see its header).
"""

import base64
import io
import os
import struct
import time
import unittest
from xml.etree import ElementTree as ET

from wcf.dictionary import inverted_dict
from wcf.records import Record, dump_records, render_xml
from wcf.session import BinaryXmlSession
from wcf.xml2records import XMLParser

FIXTURE = os.path.join(os.path.dirname(__file__), 'data', 'dotnet_wcf_messages.tsv')
# Romance Standard Time, the time zone of the host that produced them
PARIS = 'CET-1CEST,M3.5.0,M10.5.0/3'


def messages():
    with open(FIXTURE) as fp:
        for line in fp:
            mode, i, hexa, xml = line.rstrip('\n').split('\t')
            yield mode, int(i), bytes.fromhex(hexa), base64.b64decode(xml).decode()


def same_number(a, b, single):
    """Whether two lexical forms are the same double, or float32."""
    try:
        x, y = float(a), float(b)
    except ValueError:
        return False
    if single:
        return struct.pack('<f', x) == struct.pack('<f', y)
    return x == y or (x != x and y != y)  # NaN


def differences(ours, theirs, path=''):
    """The differences of two element trees; a number written differently
    (.NET Framework writes "R", not the shortest form) is the same value."""
    if ours.tag != theirs.tag or ours.attrib != theirs.attrib:
        return ['%s: %s %s != %s %s' % (path, ours.tag, ours.attrib,
                                        theirs.tag, theirs.attrib)]
    out = []
    a, b = ours.text or '', theirs.text or ''
    single = ours.tag.split('}')[-1] in ('float', 'F')
    if a != b and not same_number(a, b, single):
        out.append('%s: %r != %r' % (path, a[:60], b[:60]))
    if len(ours) != len(theirs):
        return out + ['%s: %d != %d children' % (path, len(ours), len(theirs))]
    for i, (x, y) in enumerate(zip(ours, theirs)):
        out += differences(x, y, '%s/%s[%d]' % (path, x.tag, i))
    return out


@unittest.skipUnless(hasattr(time, 'tzset'), 'needs time.tzset()')
class DotnetInteropTests(unittest.TestCase):

    def setUp(self):
        self.tz = os.environ.get('TZ')
        os.environ['TZ'] = PARIS
        time.tzset()

    def tearDown(self):
        if self.tz is None:
            del os.environ['TZ']
        else:
            os.environ['TZ'] = self.tz
        time.tzset()

    def decode(self):
        session = BinaryXmlSession()
        for mode, i, data, dotnet in messages():
            if mode == 'session':
                xml = session.parse_document(data).render_xml()
            else:
                xml = render_xml(Record.parse(io.BytesIO(data)))
            yield mode, i, data, xml, dotnet

    def test_we_read_what_dotnet_reads(self):
        count = 0
        for mode, i, data, xml, dotnet in self.decode():
            with self.subTest(mode=mode, i=i):
                self.assertEqual([], differences(ET.fromstring(xml),
                                                 ET.fromstring(dotnet)))
                count += 1
        self.assertEqual(4, count)

    def test_session_strings_are_reused(self):
        sizes = [len(data) for mode, i, data, xml, dotnet in self.decode()
                 if mode == 'session']
        self.assertGreater(sizes[0], sizes[1])  # a StringTable, then reuse

    def test_our_encodings_read_back_the_same(self):
        sender, receiver = BinaryXmlSession(), BinaryXmlSession()
        first = True
        for mode, i, data, xml, dotnet in self.decode():
            with self.subTest(mode=mode, i=i):
                if mode == 'session':
                    new = []
                    if first:
                        names = {e.tag.split('}')[-1] for e in ET.fromstring(dotnet).iter()}
                        new = sorted(n for n in names if n not in inverted_dict)
                        first = False
                    wire = sender.encode_xml(dotnet, new_strings=new)
                    back = receiver.parse_document(wire).render_xml()
                else:
                    back = render_xml(Record.parse(io.BytesIO(
                        dump_records(XMLParser.parse(dotnet)))))
                self.assertEqual([], differences(ET.fromstring(back),
                                                 ET.fromstring(dotnet)))


if __name__ == '__main__':
    unittest.main()
