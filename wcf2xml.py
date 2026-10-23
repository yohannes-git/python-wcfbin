#!/usr/bin/env python3
"""Decode MC-NBFX or MC-NBFSE (session dictionary) to character-equivalent XML."""

import argparse
import sys
from io import BytesIO

from wcf.records import NO_QUOTAS, DEFAULT_QUOTAS, Record, render_xml
from wcf.session import BinaryXmlSession


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', nargs='?', default='-',
                        help='binary input file or - for standard input')
    parser.add_argument('--nbfse', action='store_true',
                        help='read MC-NBFSE StringTable before NBFX document')
    parser.add_argument('--no-quotas', action='store_true',
                        help='no decoding quotas nor MC-NBFSE limits '
                             '(trusted input only)')
    args = parser.parse_args(argv)
    quotas = NO_QUOTAS if args.no_quotas else DEFAULT_QUOTAS
    if args.source == '-':
        data = sys.stdin.buffer.read()
    else:
        with open(args.source, 'rb') as fp:
            data = fp.read()
    try:
        if args.nbfse:
            if args.no_quotas:
                # limits that the document cannot exceed
                limit = len(data)
                session = BinaryXmlSession(
                    max_table_bytes=limit, max_strings=limit,
                    max_document_bytes=limit, max_session_bytes=limit)
            else:
                session = BinaryXmlSession()
            xml = session.parse_document(data, quotas).render_xml()
        else:
            xml = render_xml(Record.parse(BytesIO(data), quotas))
    except ValueError as error:
        parser.exit(1, '%s: error: %s\n' % (parser.prog, error))
    # UTF-8, whatever the locale: the XML has no declaration
    sys.stdout.buffer.write(xml.encode('utf-8'))


if __name__ == '__main__':
    main()
