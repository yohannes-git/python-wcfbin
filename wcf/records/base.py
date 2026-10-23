# vim: set ts=4 sw=4 tw=79 fileencoding=utf-8:
#  Copyright (c) 2011, Timo Schmid <tschmid@ernw.de>
#  All rights reserved.
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions
#  are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#  * Neither the name of the ERMW GmbH nor the names of its contributors
#    may be used to endorse or promote products derived from this software
#    without specific prior written permission.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
#  "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
#  LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
#  A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
#  HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
#  SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
#  LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
#  DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
#  THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#  (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
#  OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
from __future__ import absolute_import
from __future__ import unicode_literals

from builtins import str, bytes

import struct
import logging

from wcf.datatypes import *

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class Record(object):
    records = dict()

    @classmethod
    def add_records(cls, records):
        """adds records to the lookup table

        :param records: list of Record subclasses
        :type records: list(Record)
        """
        for r in records:
            Record.records[r.type] = r

    def __init__(self, type=None):
        if type:
            self.type = type

    def to_bytes(self):
        """
        Generates the representing bytes of the record

        >>> from wcf.records import *
        >>> Record(0xff).to_bytes()
        b'\\xff'
        >>> ElementRecord('a', 'test').to_bytes()
        b'A\\x01a\\x04test'
        """
        return bytes(struct.pack(b'<B', self.type))

    def __repr__(self):
        args = ['type=0x%X' % self.type]
        return '<%s(%s)>' % (type(self).__name__, ','.join(args))

    @classmethod
    def parse(cls, fp):
        r"""Parse a WCF Binary XML document, preserving element closure records.

        >>> from wcf.records import dump_records
        >>> from io import BytesIO
        >>> r = Record.parse(BytesIO(b'A\x01a\x04test\x01'))
        >>> dump_records(r)
        b'A\x01a\x04test\x01'
        """
        if cls is not Record:
            return cls()

        root = []
        records = root
        parents = []  # pairs of (container, open element)
        open_element = None
        while True:
            octet = fp.read(1)
            if not octet:
                break
            recordtype = octet[0]
            if recordtype in Record.records:
                recordclass = Record.records[recordtype]
                obj = recordclass.parse(fp)
                _validate_dictionary_references(obj)
                if isinstance(obj, EndElementRecord):
                    if not parents:
                        raise ValueError('Unexpected EndElement')
                    records, closed = parents.pop()
                    closed._wcf_closure = 'explicit'
                    open_element = parents[-1][1] if parents else None
                elif isinstance(obj, Element):
                    records.append(obj)
                    obj.childs = []
                    parents.append((records, obj))
                    records = obj.childs
                    open_element = obj
                elif isinstance(obj, Attribute):
                    if not open_element or records is not open_element.childs or records:
                        raise ValueError('Attribute outside element start')
                    open_element.attributes.append(obj)
                elif isinstance(obj, Text) and obj.type == 0xA6:
                    raise ValueError('EndListText without StartListText')
                else:
                    records.append(obj)
            elif (recordtype & 1 and recordtype >= 0x81 and
                  recordtype not in (0xA5, 0xA7) and
                  recordtype - 1 in Record.records and
                  issubclass(Record.records[recordtype - 1], Text)):
                if not parents:
                    raise ValueError('TextWithEndElement outside an element')
                obj = Record.records[recordtype - 1].parse(fp)
                _validate_dictionary_references(obj)
                records.append(obj)
                records, closed = parents.pop()
                closed._wcf_closure = 'implicit'
                open_element = parents[-1][1] if parents else None
            else:
                raise ValueError('Unknown or reserved WCF record 0x%02X' % recordtype)
        if parents:
            raise ValueError('Unterminated element in WCF Binary XML')
        return root



class Element(Record):
    pass


class Attribute(Record):
    pass


class Text(Record):
    pass


def validate_xml_name(name, description='name'):
    """Validate the restrictions on a MC-NBFX element/attribute name.

    A name is an XML local name here, not a qualified name.  An xmlns
    declaration is represented by its own record type, never by a regular
    element or attribute record.  The same checks apply when serializing an
    object that was modified after construction.
    """
    if not isinstance(name, str) or not name or name == 'xmlns':
        raise ValueError('Invalid MC-NBFX %s: %r' % (description, name))
    return name


def validate_dictionary_xml_name(index, description='name'):
    """Resolve an MC-NBFS/NBFSE name and apply the name restrictions."""
    from wcf.dictionary import dictionary
    # Keep KeyError for an unresolved session index: callers and the existing
    # tests use it to distinguish a missing dictionary from an invalid name.
    name = dictionary[index]
    return validate_xml_name(name, description)


def validate_attribute_text(value):
    """An attribute value MUST be one text record, not another record kind.

    EndListText is valid only as the terminator *inside* StartListText.
    """
    if (not isinstance(value, Text) or value.type == 0xA6 or
            value.type not in Record.records):
        raise ValueError('MC-NBFX attribute value must be a text record')
    return value


def read_attribute_text(fp):
    """Read and validate the value slot of any MC-NBFX attribute record."""
    octet = fp.read(1)
    if len(octet) != 1:
        raise ValueError('Truncated MC-NBFX attribute value')
    record_type = octet[0]
    record_class = Record.records.get(record_type)
    if (record_class is None or not issubclass(record_class, Text) or
            record_type == 0xA6):
        raise ValueError('Invalid MC-NBFX attribute text record 0x%02X' % record_type)
    return validate_attribute_text(record_class.parse(fp))


class EndElementRecord(Element):
    type = 0x01


class CommentRecord(Record):
    type = 0x02

    def __init__(self, comment, *args, **kwargs):
        self.comment = comment

    def to_bytes(self):
        """
        >>> CommentRecord('test').to_bytes()
        b'\\x02\\x04test'
        """
        string = Utf8String(self.comment)

        return bytes(super(CommentRecord, self).to_bytes() +
                     string.to_bytes())

    def __str__(self):
        """
        >>> str(CommentRecord('test'))
        '<!-- test -->'
        """
        return '<!-- %s -->' % self.comment

    @classmethod
    def parse(cls, fp):
        data = Utf8String.parse(fp).value
        return cls(data)


class ArrayRecord(Record):
    type = 0x03

    datatypes = {
        0xB5: ('BoolTextWithEndElement', 1, '?'),
        0x8B: ('Int16TextWithEndElement', 2, 'h'),
        0x8D: ('Int32TextWithEndElement', 4, 'i'),
        0x8F: ('Int64TextWithEndElement', 8, 'q'),
        0x91: ('FloatTextWithEndElement', 4, 'f'),
        0x93: ('DoubleTextWithEndElement', 8, 'd'),
        0x95: ('DecimalTextWithEndElement', 16, ''),
        0x97: ('DateTimeTextWithEndElement', 8, ''),
        0xAF: ('TimeSpanTextWithEndElement', 8, ''),
        0xB1: ('UuidTextWithEndElement', 16, ''),
    }

    def __init__(self, element, data, attributes):
        self.element = element
        self.count = len(data)
        self.data = data
        recordtype = None
        for data in self.data:
            if recordtype is None:
                recordtype = data.type + 1
            else:
                if recordtype != data.type + 1:
                    raise ValueError('ArrayRecord requires a single type')
        self.recordtype = recordtype
        self.attributes = list(attributes)
        if self.count == 0 or self.recordtype not in self.datatypes:
            raise ValueError('ArrayRecord requires a non-empty, supported typed array')

    def to_bytes(self):
        """
        >>> from wcf.records.text import Int32TextRecord
        >>> from wcf.records.elements import ShortElementRecord
        >>> ArrayRecord(ShortElementRecord('item'), [Int32TextRecord(1), Int32TextRecord(2), Int32TextRecord(3)], []).to_bytes()
        b'\\x03@\\x04item\\x01\\x8d\\x03\\x01\\x00\\x00\\x00\\x02\\x00\\x00\\x00\\x03\\x00\\x00\\x00'
        """
        bt = super(ArrayRecord, self).to_bytes()
        bt += self.element.to_bytes()
        for attrib in self.attributes:
            bt += attrib.to_bytes()
        bt += EndElementRecord().to_bytes()
        if not self.data:
            raise ValueError('ArrayRecord cannot be empty')
        expected = self.data[0].type + 1
        if expected not in self.datatypes or any(item.type + 1 != expected for item in self.data):
            raise ValueError('ArrayRecord requires one supported element type')
        bt += bytes(struct.pack(b'<B', expected))
        bt += MultiByteInt31(len(self.data)).to_bytes()
        for data in self.data:
            bt += data.to_bytes()[1:]
        return bytes(bt)

    @classmethod
    def parse(cls, fp):
        """
        >>> from wcf.records import *
        >>> from io import BytesIO
        >>> buf = BytesIO(b'@\\x04item\\x01\\x8d\\x03\\x01\\x00\\x00\\x00\\x02\\x00\\x00\\x00\\x03\\x00\\x00\\x00')
        >>> r = ArrayRecord.parse(buf)
        >>> r
        <ArrayRecord(type=0x3)>
        >>> r.to_bytes()
        b'\\x03@\\x04item\\x01\\x8d\\x03\\x01\\x00\\x00\\x00\\x02\\x00\\x00\\x00\\x03\\x00\\x00\\x00'
        """
        octet = fp.read(1)
        if len(octet) != 1:
            raise ValueError('Truncated ArrayRecord element')
        element_type = octet[0]
        element_class = Record.records.get(element_type)
        if element_class is None or not issubclass(element_class, Element) or element_type == EndElementRecord.type:
            raise ValueError('Invalid ArrayRecord element type 0x%02X' % element_type)
        element = element_class.parse(fp)
        attributes = []
        while True:
            octet = fp.read(1)
            if len(octet) != 1:
                raise ValueError('Truncated ArrayRecord attributes')
            type = octet[0]
            record_class = Record.records.get(type)
            if record_class is None:
                raise ValueError('Unknown ArrayRecord attribute type 0x%02X' % type)
            obj = record_class.parse(fp)
            if isinstance(obj, EndElementRecord):
                break
            elif isinstance(obj, Attribute):
                attributes.append(obj)
            else:
                raise ValueError('unknown type: %s' % hex(type))
        octet = fp.read(1)
        if len(octet) != 1:
            raise ValueError('Truncated ArrayRecord data type')
        recordtype = octet[0]
        if recordtype not in cls.datatypes:
            raise ValueError('Unsupported ArrayRecord type 0x%02X' % recordtype)
        count = MultiByteInt31.parse(fp).value
        if count == 0:
            raise ValueError('ArrayRecord length cannot be zero')
        data = []
        for i in range(count):
            data.append(Record.records[recordtype-1].parse(fp))
        return cls(element, data, attributes)

    def __str__(self):
        """
        >>> from wcf.records.elements import ShortElementRecord
        >>> from wcf.records.text import Int32TextRecord
        >>> str(ArrayRecord(ShortElementRecord('item'), [Int32TextRecord(1), Int32TextRecord(2), Int32TextRecord(3)], []))
        '<item>1</item><item>2</item><item>3</item>'
        """
        from xml.sax.saxutils import escape
        name = ('%s:%s' % (self.element.prefix, self.element.name)
                if hasattr(self.element, 'prefix') else self.element.name)
        opening = str(self.element)
        if self.attributes:
            opening = opening[:-1] + ' ' + ' '.join(map(str, self.attributes)) + '>'
        return ''.join(opening + escape(str(data)) + '</%s>' % name
                       for data in self.data)



def _validate_dictionary_references(record):
    """Reject dictionary indices not defined in static/session dictionaries.

    Element constructors already resolve their IDs, but attribute and text
    records historically deferred lookup to ``str``/rendering.  Accepting an
    unknown ID as a parsed record would make decoding depend on later state.
    """
    from wcf.dictionary import dictionary
    if isinstance(record, Record) and hasattr(record, 'index'):
        dictionary[record.index]
    if isinstance(record, ArrayRecord):
        _validate_dictionary_references(record.element)
        for attr in record.attributes:
            _validate_dictionary_references(attr)
        for value in record.data:
            _validate_dictionary_references(value)
    elif isinstance(record, Attribute) and hasattr(record, 'value'):
        _validate_dictionary_references(record.value)
    elif isinstance(record, Text) and hasattr(record, 'values'):
        for value in record.values:
            _validate_dictionary_references(value)


Record.add_records((EndElementRecord,
        CommentRecord,
        ArrayRecord,))
