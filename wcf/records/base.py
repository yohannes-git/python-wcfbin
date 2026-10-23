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
"""Record classes, the document parser and its decoding quotas."""

import dataclasses
import struct
import string
from contextvars import ContextVar

from wcf.errors import WcfBinaryError, binary_errors
from wcf.datatypes import (MultiByteInt31, mbi31_bytes, read_exact, read_mbi31,
                           read_utf8, utf8_bytes)
from wcf.dictionary import dictionary
from wcf.xmltext import comment, escape_attribute, ncname

__all__ = ['Record', 'Element', 'Attribute', 'Text', 'EndElementRecord',
           'CommentRecord', 'ArrayRecord', 'Quotas', 'DEFAULT_QUOTAS',
           'NO_QUOTAS', 'validate_xml_name', 'validate_dictionary_xml_name',
           'validate_attribute_text', 'read_attribute_text']


@dataclasses.dataclass(frozen=True)
class Quotas:
    """Limits on the decoding of one document (immutable: DEFAULT_QUOTAS is
    shared by every caller).

    MC-NBFX and MC-NBFSE (section 4) ask consumers to guard against
    documents that cost far more than their size: a two-byte
    DictionaryText can stand for a long dictionary string, every record
    becomes an object, and nesting has no bound. These quotas play the
    role of .NET's XmlDictionaryReaderQuotas; a document exceeding one
    is refused with WcfBinaryError while it is being parsed.

    max_depth:   maximum element nesting (MaxDepth).
    max_records: maximum number of records, every attribute, list item
                 and array item counted.
    max_chars:   maximum number of characters the document represents:
                 names, prefixes, namespace URIs, comments and values,
                 dictionary strings expanded, element names counted
                 twice (start and end tags) and array items repeated.
                 render_xml() adds the markup and the escaping (up to
                 6 characters for one, "&quot;"), so its output is
                 bounded by a small multiple of max_chars.

    None disables a limit.
    """
    max_depth: int = 64
    max_records: int = 200000
    max_chars: int = 16 * 1024 * 1024


DEFAULT_QUOTAS = Quotas()
NO_QUOTAS = Quotas(None, None, None)


class _Budget(object):
    """What the document being decoded has used of its quotas."""

    __slots__ = ('quotas', 'records', 'chars', '_max_records', '_max_chars')

    def __init__(self, quotas):
        self.quotas = quotas
        self.records = 0
        self.chars = 0
        inf = float('inf')
        self._max_records = inf if quotas.max_records is None else quotas.max_records
        self._max_chars = inf if quotas.max_chars is None else quotas.max_chars

    def charge(self, records, chars):
        self.records += records
        self.chars += chars
        if self.records > self._max_records:
            raise WcfBinaryError('MC-NBFX document exceeds the quota of %d records'
                             % self.quotas.max_records)
        if self.chars > self._max_chars:
            raise WcfBinaryError('MC-NBFX document exceeds the quota of %d characters'
                             % self.quotas.max_chars)


_budget = ContextVar('wcf_decoding_budget', default=None)


def charge(records, chars):
    """Account for records about to be created by the parse in progress.

    Array and list items are charged before they are read, so that a
    count that exceeds a quota is refused before anything is allocated.
    """
    budget = _budget.get()
    if budget is not None:
        budget.charge(records, chars)


class Record(object):
    """A record. ``Record.records`` maps the record types to their
    classes; ``Record.parse()`` parses a whole document."""
    records = {}

    @classmethod
    def add_records(cls, records):
        """Register record classes by their type."""
        for r in records:
            if Record.records.get(r.type, r) is not r:
                raise RuntimeError('MC-NBFX record type 0x%02X registered twice'
                                   % r.type)
            Record.records[r.type] = r

    def to_bytes(self):
        """
        Generates the representing bytes of the record

        >>> from wcf.records import *
        >>> ZeroTextRecord().to_bytes()
        b'\\x80'
        >>> ElementRecord('a', 'test').to_bytes()
        b'A\\x01a\\x04test'
        """
        return bytes((self.type,))

    def __repr__(self):
        return '<%s(type=0x%X)>' % (type(self).__name__, self.type)

    @classmethod
    def parse(cls, fp, quotas=DEFAULT_QUOTAS):
        r"""Parse a WCF Binary XML document, preserving element closure records.

        The document is refused with WcfBinaryError when it exceeds one of
        the ``quotas`` (DEFAULT_QUOTAS unless given, NO_QUOTAS for
        trusted input only). On a record class, parse() reads the record
        after its type: here, a record without fields.

        >>> from wcf.records import dump_records
        >>> from io import BytesIO
        >>> r = Record.parse(BytesIO(b'A\x01a\x04test\x01'))
        >>> dump_records(r)
        b'A\x01a\x04test\x01'
        """
        if cls is not Record:
            return cls()

        budget = _Budget(quotas)
        token = _budget.set(budget)
        try:
            with binary_errors():
                return cls._parse_document(fp, quotas.max_depth, budget)
        finally:
            _budget.reset(token)

    @staticmethod
    def _parse_document(fp, max_depth, budget):
        root = []
        records = root
        parents = []  # pairs of (container, open element)
        open_element = None
        read = fp.read
        registry = Record.records
        charge = budget.charge
        if max_depth is None:
            max_depth = float('inf')
        while True:
            octet = read(1)
            if not octet:
                break
            record_class = registry.get(octet[0])
            if record_class is not None:
                what = record_class._kind
                if what is _TEXT and not record_class.standalone:
                    raise WcfBinaryError('EndListText without StartListText')
            else:
                # *TextWithEndElement: the type after that of its text record
                record_class = registry.get(octet[0] - 1)
                if (not octet[0] & 1 or record_class is None or
                        record_class._kind is not _TEXT or
                        not record_class.with_end_element):
                    raise WcfBinaryError('Unknown or reserved WCF record 0x%02X'
                                         % octet[0])
                what = _TEXT_END
            obj = record_class.parse(fp)
            if what is _TEXT:
                charge(1, obj.char_count())
                records.append(obj)
            elif what is _ELEMENT:
                charge(1, 2 * _name_chars(obj))  # start and end tags
                if len(parents) >= max_depth:
                    raise WcfBinaryError('MC-NBFX document nested deeper than %d'
                                         % max_depth)
                records.append(obj)
                parents.append((records, obj))
                records = obj.childs
                open_element = obj
            elif what is _TEXT_END:
                if not parents:
                    raise WcfBinaryError('TextWithEndElement outside an element')
                charge(1, obj.char_count())
                records.append(obj)
                records, closed = parents.pop()
                closed._wcf_closure = 'implicit'
                open_element = parents[-1][1] if parents else None
            elif what is _ATTRIBUTE:
                charge(*_attribute_cost(obj))
                if not open_element or records is not open_element.childs or records:
                    raise WcfBinaryError('Attribute outside element start')
                open_element.attributes.append(obj)
            elif what is _END:
                if not parents:
                    raise WcfBinaryError('Unexpected EndElement')
                records, closed = parents.pop()
                closed._wcf_closure = 'explicit'
                open_element = parents[-1][1] if parents else None
            else:
                if what is _COMMENT:
                    charge(1, len(obj.comment))
                records.append(obj)  # arrays are charged by their parse()
        if parents:
            raise WcfBinaryError('Unterminated element in WCF Binary XML')
        return root


# the kinds of record (Record._kind): one class attribute read per record
# instead of an isinstance() cascade, and no cache to keep in sync
_OTHER, _TEXT, _TEXT_END, _ELEMENT, _ATTRIBUTE, _END, _COMMENT, _ARRAY = (
    'other', 'text', 'text+end', 'element', 'attribute', 'end', 'comment',
    'array')
Record._kind = _OTHER


class Element(Record):
    """An element record: ``prefix`` (None without), ``name``,
    ``attributes`` and ``childs``. ``_wcf_closure`` is how a decoded
    element was closed: 'explicit' (EndElement) or 'implicit'
    (*TextWithEndElement), kept when it is serialized again."""
    prefix = None
    _wcf_closure = None
    _kind = _ELEMENT

    @property
    def qname(self):
        return self.name if self.prefix is None else '%s:%s' % (self.prefix, self.name)

    def __str__(self):
        """The start tag.

        >>> from wcf.records import *
        >>> e = ShortElementRecord('a')
        >>> e.attributes.append(ShortAttributeRecord('b', Chars8TextRecord('"<')))
        >>> str(e)
        '<a b="&quot;&lt;">'
        """
        return start_tag(self)


class Attribute(Record):
    """An attribute record: ``prefix`` (None without), ``name`` and
    ``value`` (a text record); or, for a namespace declaration
    (``is_xmlns``), ``prefix`` (None for the default namespace) and
    ``namespace``."""
    prefix = None
    is_xmlns = False
    _kind = _ATTRIBUTE

    @property
    def qname(self):
        return self.name if self.prefix is None else '%s:%s' % (self.prefix, self.name)

    def __str__(self):
        return attribute_xml(self)[1:]


class Text(Record):
    """A text record. ``max_chars`` is the length of the longest rendering
    of a fixed-size type (None for the others), ``standalone`` False for
    EndListText (only valid closing a list) and ``with_end_element`` False
    for the records without a *WithEndElement form (StartListText,
    EndListText)."""
    max_chars = None
    standalone = True
    with_end_element = True
    _kind = _TEXT

    def char_count(self):
        """The number of characters represented, or an upper bound."""
        if self.max_chars is not None:
            return self.max_chars
        return len(str(self))


class EndElementRecord(Record):
    type = 0x01
    _kind = _END


def validate_xml_name(name, description='name'):
    """Validate the restrictions on a MC-NBFX element/attribute name.

    A name is an XML local name here, not a qualified name.  An xmlns
    declaration is represented by its own record type, never by a regular
    element or attribute record.  The same checks apply when serializing an
    object that was modified after construction.
    """
    if not isinstance(name, str) or not name or name == 'xmlns':
        raise WcfBinaryError('Invalid MC-NBFX %s: %r' % (description, name))
    return name


def validate_dictionary_xml_name(index, description='name'):
    """Resolve an MC-NBFS/NBFSE name and apply the name restrictions."""
    return validate_xml_name(dictionary[index], description)


def validate_attribute_text(value):
    """An attribute value MUST be one text record, not another record kind.

    EndListText is valid only as the terminator *inside* StartListText.
    """
    if (not isinstance(value, Text) or not value.standalone or
            value.type not in Record.records):
        raise WcfBinaryError('MC-NBFX attribute value must be a text record')
    return value


def read_attribute_text(fp):
    """Read and validate the value slot of any MC-NBFX attribute record."""
    octet = fp.read(1)
    if len(octet) != 1:
        raise WcfBinaryError('Truncated MC-NBFX attribute value')
    record_class = Record.records.get(octet[0])
    if (record_class is None or not issubclass(record_class, Text) or
            not record_class.standalone):
        raise WcfBinaryError('Invalid MC-NBFX attribute text record 0x%02X' % octet[0])
    return record_class.parse(fp)


class _DictionaryName(object):
    """The name of a record that stores it as a DictionaryString, resolved
    on use so that it always matches the index that is written."""

    @property
    def name(self):
        return dictionary[self.index]


class _NamedRecord(Record):
    """The names of the element and attribute records: a prefix, which is
    a String (``_has_prefix``), the letter of a Prefix* record type (the
    ``prefix`` class attribute) or none, then a name, which is a String or
    a DictionaryString (``_by_index``, with _DictionaryName)."""
    _has_prefix = False
    _by_index = False
    _what = 'name'

    def _set_names(self, names):
        if len(names) != self._has_prefix + 1:
            raise TypeError('%s takes %d name argument(s)'
                            % (type(self).__name__, self._has_prefix + 1))
        if self._has_prefix:
            self.prefix = validate_xml_name(names[0], self._what + ' prefix')
        if self._by_index:
            self.index = names[-1]
            validate_dictionary_xml_name(self.index, self._what + ' name')
        else:
            self.name = validate_xml_name(names[-1], self._what + ' name')

    def _head(self):
        """The record type and the names."""
        out = [bytes((self.type,))]
        if self._has_prefix:
            out.append(utf8_bytes(validate_xml_name(self.prefix, self._what + ' prefix')))
        if self._by_index:
            validate_dictionary_xml_name(self.index, self._what + ' name')
            out.append(mbi31_bytes(self.index))
        else:
            out.append(utf8_bytes(validate_xml_name(self.name, self._what + ' name')))
        return out

    @classmethod
    def _read_names(cls, fp):
        names = [read_utf8(fp)] if cls._has_prefix else []
        names.append(read_mbi31(fp) if cls._by_index
                     else read_utf8(fp))
        return names


def letter_records(base, first_type, name_format, namespace):
    """Define the 26 classes of ``base`` whose prefix is the letter of
    their record type (first_type for "a" to first_type + 25 for "z") in
    ``namespace`` (and its __all__), register them, and return them by
    letter."""
    classes = {}
    for i, letter in enumerate(string.ascii_lowercase):
        name = name_format % letter.upper()
        classes[letter] = type(name, (base,), {
            'type': first_type + i, 'prefix': letter, 'char': letter,
            '__module__': namespace['__name__'], '__qualname__': name})
    namespace.update((c.__name__, c) for c in classes.values())
    namespace['__all__'].extend(c.__name__ for c in classes.values())
    Record.add_records(classes.values())
    return classes


class CommentRecord(Record):
    type = 0x02
    _kind = _COMMENT

    def __init__(self, comment):
        self.comment = comment

    def to_bytes(self):
        """
        >>> CommentRecord('test').to_bytes()
        b'\\x02\\x04test'
        """
        return bytes((self.type,)) + utf8_bytes(self.comment)

    def __str__(self):
        """
        >>> str(CommentRecord('test'))
        '<!--test-->'
        """
        return comment(self.comment)

    @classmethod
    def parse(cls, fp):
        return cls(read_utf8(fp))


class ArrayRecord(Record):
    """MC-NBFX 2.3.3: an element (with its attributes) repeated for each
    value of a typed array."""
    type = 0x03
    _kind = _ARRAY

    # the *TextWithEndElement record types an array can hold
    datatypes = frozenset((0xB5, 0x8B, 0x8D, 0x8F, 0x91, 0x93, 0x95, 0x97,
                           0xAF, 0xB1))

    def __init__(self, element, data, attributes):
        self.element = element
        self.data = data
        self.attributes = list(attributes)
        self.recordtype = self._check()

    def _check(self):
        """The *WithEndElement record type of the items."""
        if not self.data:
            raise WcfBinaryError('ArrayRecord cannot be empty')
        record_type = self.data[0].type + 1
        if (record_type not in self.datatypes or
                any(item.type + 1 != record_type for item in self.data)):
            raise WcfBinaryError('ArrayRecord requires one supported element type')
        return record_type

    def to_bytes(self):
        """
        >>> from wcf.records.text import Int32TextRecord
        >>> from wcf.records.elements import ShortElementRecord
        >>> ArrayRecord(ShortElementRecord('item'), [Int32TextRecord(1), Int32TextRecord(2), Int32TextRecord(3)], []).to_bytes()
        b'\\x03@\\x04item\\x01\\x8d\\x03\\x01\\x00\\x00\\x00\\x02\\x00\\x00\\x00\\x03\\x00\\x00\\x00'
        """
        out = bytearray((self.type,))
        out += self.element.to_bytes()
        for attribute in self.attributes:
            out += attribute.to_bytes()
        out.append(EndElementRecord.type)
        out.append(self._check())
        out += MultiByteInt31(len(self.data)).to_bytes()
        for item in self.data:
            out += item.to_bytes()[1:]
        return bytes(out)

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
            raise WcfBinaryError('Truncated ArrayRecord element')
        element_class = Record.records.get(octet[0])
        if element_class is None or not issubclass(element_class, Element):
            raise WcfBinaryError('Invalid ArrayRecord element type 0x%02X' % octet[0])
        element = element_class.parse(fp)
        attributes = []
        while True:
            octet = fp.read(1)
            if len(octet) != 1:
                raise WcfBinaryError('Truncated ArrayRecord attributes')
            if octet[0] == EndElementRecord.type:
                break
            # the type is checked before the record is read: another Array
            # here would recurse without bound
            record_class = Record.records.get(octet[0])
            if record_class is None or not issubclass(record_class, Attribute):
                raise WcfBinaryError('Invalid ArrayRecord attribute record 0x%02X'
                                 % octet[0])
            attribute = record_class.parse(fp)
            # charged as they are read, not once all are allocated
            charge(*_attribute_cost(attribute))
            attributes.append(attribute)
        octet = fp.read(1)
        if len(octet) != 1:
            raise WcfBinaryError('Truncated ArrayRecord data type')
        if octet[0] not in cls.datatypes:
            raise WcfBinaryError('Unsupported ArrayRecord type 0x%02X' % octet[0])
        item_class = Record.records[octet[0] - 1]
        count = read_mbi31(fp)
        if count == 0:
            raise WcfBinaryError('ArrayRecord length cannot be zero')
        # every item stands for <name attributes>value</name>
        item_records, item_chars = 1, 2 * _name_chars(element) + item_class.max_chars
        for attribute in attributes:
            records, chars = _attribute_cost(attribute)
            item_records += records
            item_chars += chars
        charge(count * item_records, count * item_chars)
        from wcf.records.text import _FixedSizeText
        if item_class.parse.__func__ is _FixedSizeText.parse.__func__:
            # fixed-size items without validation of their own: one read,
            # one unpack (the count is already charged)
            packer = struct.Struct(item_class._format)
            data = read_exact(fp, count * packer.size)
            return cls(element, [item_class(value) for (value,)
                                 in packer.iter_unpack(data)], attributes)
        return cls(element, [item_class.parse(fp) for _ in range(count)], attributes)

    def __str__(self):
        """
        >>> from wcf.records.elements import ShortElementRecord
        >>> from wcf.records.text import Int32TextRecord
        >>> str(ArrayRecord(ShortElementRecord('item'), [Int32TextRecord(1), Int32TextRecord(2), Int32TextRecord(3)], []))
        '<item>1</item><item>2</item><item>3</item>'
        """
        from wcf.records import render_xml
        return render_xml([self])


# --- XML of the element and attribute records -----------------------------

def qualified_name(record):
    """The qualified name of an element or attribute record, WcfBinaryError if
    XML cannot carry it."""
    name = ncname(record.name)
    return name if record.prefix is None else '%s:%s' % (ncname(record.prefix), name)


def attribute_xml(attribute):
    """' name="value"' for an attribute record."""
    if attribute.is_xmlns:
        name = ('xmlns' if attribute.prefix is None
                else 'xmlns:' + ncname(attribute.prefix))
        value = attribute.namespace
    else:
        name = qualified_name(attribute)
        value = str(attribute.value)
    return ' %s="%s"' % (name, escape_attribute(value))


def start_tag(element, attributes=()):
    """The start tag of an element record, with extra ``attributes``."""
    return '<%s%s>' % (qualified_name(element),
                       ''.join(attribute_xml(a) for a in
                               list(element.attributes) + list(attributes)))


# --- decoding cost --------------------------------------------------------

def _name_chars(record):
    """Characters of the qualified name of an element or attribute record
    (resolving a dictionary name rejects an unknown id)."""
    count = len(record.name)
    return count if record.prefix is None else count + len(record.prefix) + 1


def _attribute_cost(record):
    """(records, characters) of an attribute record and its value."""
    if record.is_xmlns:
        return 1, len(record.prefix or '') + len(record.namespace)
    return 2, _name_chars(record) + record.value.char_count()


Record.add_records((EndElementRecord, CommentRecord, ArrayRecord))
