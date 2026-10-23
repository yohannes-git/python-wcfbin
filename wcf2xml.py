#!/usr/bin/env python3
"""Decode MC-NBFX or MC-NBFSE (session dictionary) to character-equivalent XML."""

import argparse
import sys
from io import BytesIO

from wcf.records import Record, render_xml
from wcf.session import BinaryXmlSession


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', nargs='?', default='-',
                        help='binary input file or - for standard input')
    parser.add_argument('--nbfse', action='store_true',
                        help='read MC-NBFSE StringTable before NBFX document')
    args = parser.parse_args(argv)
    if args.source == '-':
        data = sys.stdin.buffer.read()
    else:
        with open(args.source, 'rb') as fp:
            data = fp.read()
    if args.nbfse:
        xml = BinaryXmlSession().parse_document(data).render_xml()
    else:
        xml = render_xml(Record.parse(BytesIO(data)))
    sys.stdout.write(xml)


if __name__ == '__main__':
    main()
