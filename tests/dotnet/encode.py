#!/usr/bin/env python3
"""Encode, with this library, the messages of a "run.ps1 -Mode produce"
output, for "run.ps1 -Mode consume" (see run.ps1).

    python3 tests/dotnet/encode.py messages.tsv dotnet > python.tsv
    python3 tests/dotnet/encode.py messages.tsv python > python.tsv

"dotnet" encodes the XML that .NET read from each message; "python"
decodes each message with this library and encodes its rendering
(.NET -> python -> .NET). The messages of the "session" mode share one
MC-NBFSE session per direction; the first one declares the names of the
contract in its StringTable, the following ones refer to them.
"""

import base64
import io
import os
import sys
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from wcf.dictionary import inverted_dict  # noqa: E402
from wcf.records import Record, dump_records, render_xml  # noqa: E402
from wcf.session import BinaryXmlSession  # noqa: E402
from wcf.xml2records import XMLParser  # noqa: E402


def main(path, source):
    decoder, encoder = BinaryXmlSession(), BinaryXmlSession()
    first = True
    with open(path) as fp:
        for line in fp:
            mode, i, hexa, xml64 = line.rstrip('\n').split('\t')
            if source == 'dotnet':
                xml = base64.b64decode(xml64).decode()
            elif mode == 'session':
                xml = decoder.parse_document(bytes.fromhex(hexa)).render_xml()
            else:
                xml = render_xml(Record.parse(io.BytesIO(bytes.fromhex(hexa))))
            if mode == 'session':
                new = []
                if first:
                    names = {e.tag.split('}')[-1] for e in ET.fromstring(xml).iter()}
                    new = sorted(n for n in names if n not in inverted_dict)
                    first = False
                data = encoder.encode_xml(xml, new_strings=new)
            else:
                data = dump_records(XMLParser.parse(xml))
            sys.stdout.write('%s\t%s\t%s\n' % (mode, i, data.hex()))


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[2] not in ('dotnet', 'python'):
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
