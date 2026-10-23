#!/usr/bin/env python3
"""Convert XML to MC-NBFX or MC-NBFSE (session dictionary) binary."""

import argparse
import json
import sys

from wcf.xml2records import XMLParser
from wcf.records import dump_records
from wcf.session import BinaryXmlSession


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', nargs='?', default='-',
                        help='XML input file or - for standard input')
    parser.add_argument('--types', metavar='JSON',
                        help='optional explicit WCF types keyed by expanded XML path')
    parser.add_argument('--nbfse', action='store_true',
                        help='write MC-NBFSE StringTable before NBFX document')
    parser.add_argument('--new-strings', metavar='JSON',
                        help='JSON list of new MC-NBFSE session strings for this document')
    args = parser.parse_args(argv)
    type_overrides = {}
    if args.types:
        with open(args.types, 'r', encoding='utf-8') as fp:
            type_overrides = json.load(fp)
        if not isinstance(type_overrides, dict):
            parser.error('--types must contain a JSON object')
    new_strings = []
    if args.new_strings:
        if not args.nbfse:
            parser.error('--new-strings requires --nbfse')
        with open(args.new_strings, 'r', encoding='utf-8') as fp:
            new_strings = json.load(fp)
        if not isinstance(new_strings, list) or not all(
                isinstance(item, str) for item in new_strings):
            parser.error('--new-strings must contain a JSON list of strings')
    if args.source == '-':
        source = sys.stdin.buffer.read()
    else:
        with open(args.source, 'rb') as fp:
            source = fp.read()
    try:
        if args.nbfse:
            output = BinaryXmlSession().encode_xml(source, new_strings,
                                                   type_overrides=type_overrides)
        else:
            output = dump_records(XMLParser.parse(source, type_overrides=type_overrides))
    except ValueError as error:
        parser.exit(1, '%s: error: %s\n' % (parser.prog, error))
    sys.stdout.buffer.write(output)


if __name__ == '__main__':
    main()
