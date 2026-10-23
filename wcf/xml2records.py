"""XML -> MC-NBFX record tree.

Ordinary XML supplies *lexical text*, not WCF wire types.  By default every
text or attribute value is written as a UTF-8 Chars record; optional explicit
type overrides are keyed by an XML namespace-aware path.
"""


import base64
import math
import re
import struct
from xml.parsers import expat

from wcf.errors import WcfBinaryError, binary_errors
from wcf.dictionary import inverted_dict
from wcf.xmltext import XML_WHITESPACE, ncname
from wcf.records import (
    ShortElementRecord, ElementRecord, ShortDictionaryElementRecord,
    DictionaryElementRecord, ShortAttributeRecord, AttributeRecord,
    ShortDictionaryAttributeRecord, DictionaryAttributeRecord,
    ShortXmlnsAttributeRecord, XmlnsAttributeRecord,
    ShortDictionaryXmlnsAttributeRecord, DictionaryXmlnsAttributeRecord,
    Chars8TextRecord, Chars16TextRecord, Chars32TextRecord,
    Int8TextRecord, Int16TextRecord, Int32TextRecord, Int64TextRecord,
    UInt64TextRecord, FloatTextRecord, DoubleTextRecord, DecimalTextRecord,
    BoolTextRecord, UuidTextRecord, UniqueIdTextRecord,
    Bytes8TextRecord, Bytes16TextRecord, Bytes32TextRecord, DictionaryTextRecord,
    CommentRecord,
)
from wcf.datatypes import Decimal
from wcf.records.attributes import PREFIX_ATTRIBUTES, PREFIX_DICTIONARY_ATTRIBUTES
from wcf.records.elements import PREFIX_ELEMENTS, PREFIX_DICTIONARY_ELEMENTS

__all__ = ['XMLParser']

# the record families of a name, by (prefix kind, dictionary name):
# (no prefix, string prefix, letter prefix) x (String, DictionaryString)
_ELEMENT_RECORDS = ((ShortElementRecord, ShortDictionaryElementRecord),
                    (ElementRecord, DictionaryElementRecord),
                    (PREFIX_ELEMENTS, PREFIX_DICTIONARY_ELEMENTS))
_ATTRIBUTE_RECORDS = ((ShortAttributeRecord, ShortDictionaryAttributeRecord),
                      (AttributeRecord, DictionaryAttributeRecord),
                      (PREFIX_ATTRIBUTES, PREFIX_DICTIONARY_ATTRIBUTES))


def _named_record(qname, families, *value):
    """The most compact element or attribute record for an XML qualified
    name: a dictionary name when the active dictionaries have it, the
    single letter prefix records for a prefix a to z."""
    prefix, colon, name = qname.rpartition(':')
    ncname(name)
    index = inverted_dict.get(name)
    by_index = index is not None
    if not colon:
        return families[0][by_index](index if by_index else name, *value)
    ncname(prefix)
    if len(prefix) == 1 and 'a' <= prefix <= 'z':
        return families[2][by_index][prefix](index if by_index else name, *value)
    return families[1][by_index](prefix, index if by_index else name, *value)


_INT_TYPES = {
    'int8': (Int8TextRecord, -128, 127),
    'int16': (Int16TextRecord, -(1 << 15), (1 << 15) - 1),
    'int32': (Int32TextRecord, -(1 << 31), (1 << 31) - 1),
    'int64': (Int64TextRecord, -(1 << 63), (1 << 63) - 1),
    'uint64': (UInt64TextRecord, 0, (1 << 64) - 1),
}
_XML_NS = 'http://www.w3.org/XML/1998/namespace'


def _as_qname(name, ns, is_attribute=False):
    if ':' in name:
        prefix, local = name.split(':', 1)
        if prefix not in ns:
            raise WcfBinaryError('Undeclared XML namespace prefix: %s' % prefix)
        uri = ns[prefix]
    else:
        local = name
        uri = '' if is_attribute else ns.get('', '')
    return '{%s}%s' % (uri, local) if uri else local


def _smallest_record(classes, value, length):
    """The record of ``classes`` with the smallest length field that can
    hold ``length`` bytes."""
    for record in classes:
        if length <= _MAX_LENGTH[record]:
            return record(value)
    raise WcfBinaryError('%s too long (%d bytes)' % (classes[-1].__name__, length))


_MAX_LENGTH = {record: record.max_length() for record in (
    Chars8TextRecord, Chars16TextRecord, Chars32TextRecord,
    Bytes8TextRecord, Bytes16TextRecord, Bytes32TextRecord)}


def _choose_chars_record(data):
    # at most 4 UTF-8 bytes per character: short strings are not encoded
    if len(data) <= 0x3f:
        return Chars8TextRecord(data)
    return _smallest_record((Chars8TextRecord, Chars16TextRecord,
                             Chars32TextRecord), data,
                            len(data) if data.isascii() else len(data.encode('utf-8')))


def _choose_bytes_record(value):
    return _smallest_record((Bytes8TextRecord, Bytes16TextRecord,
                             Bytes32TextRecord), value, len(value))


_UUID = re.compile('[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}')


def _typed_text(value, kind):
    """Build a typed record only when the caller knows the expected type."""
    kind = kind.lower()
    if kind in ('text', 'string', 'chars'):
        return _choose_chars_record(value)
    stripped = value.strip(XML_WHITESPACE)
    if kind in _INT_TYPES:
        record, minval, maxval = _INT_TYPES[kind]
        if not re.fullmatch(r'[+-]?[0-9]+', stripped):
            raise WcfBinaryError('Invalid %s value %r' % (kind, value))
        n = int(stripped)
        if not minval <= n <= maxval:
            raise WcfBinaryError('%s out of range: %r' % (kind, value))
        return record(n)
    if kind in ('bool', 'boolean'):
        if stripped in ('true', '1'):
            return BoolTextRecord(True)
        if stripped in ('false', '0'):
            return BoolTextRecord(False)
        raise WcfBinaryError('Invalid boolean literal %r' % value)
    if kind in ('float', 'double'):
        if stripped in ('INF', '+INF'):
            n = float('inf')
        elif stripped == '-INF':
            n = float('-inf')
        elif stripped == 'NaN':
            n = float('nan')
        elif re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?',
                          stripped):
            n = float(stripped)
            # a finite literal beyond the range is refused, not made INF
            # (a float rounds to float32, as .NET's float.MaxValue written
            # "3.40282347E+38" does)
            try:
                if math.isinf(n) or kind == 'float' and math.isinf(
                        struct.unpack('<f', struct.pack('<f', n))[0]):
                    raise OverflowError
            except OverflowError:
                raise WcfBinaryError('%s out of range: %r' % (kind, value)) from None
        else:
            raise WcfBinaryError('Invalid floating-point literal %r' % value)
        return FloatTextRecord(n) if kind == 'float' else DoubleTextRecord(n)
    if kind == 'decimal':
        return DecimalTextRecord(Decimal.from_string(stripped))
    if kind in ('uuid', 'uniqueid'):
        # the text that the record renders; uuid.UUID() would also take
        # braces, no hyphens, "+", "_" or "0x" in a group, other scripts
        prefix = 'urn:uuid:' if kind == 'uniqueid' else ''
        if not stripped.startswith(prefix) or \
                not _UUID.fullmatch(stripped[len(prefix):]):
            raise WcfBinaryError('Invalid %s value %r' % (kind, value))
        return (UuidTextRecord if kind == 'uuid' else UniqueIdTextRecord)(stripped)
    if kind in ('base64', 'bytes'):
        # Whitespace is permitted in XML Schema base64 lexical values.
        clean = re.sub('[%s]' % XML_WHITESPACE, '', stripped)
        return _choose_bytes_record(base64.b64decode(clean, validate=True))
    raise WcfBinaryError('Unsupported explicit WCF type %r' % kind)


class XMLParser(object):
    """Strict XML input with namespace-aware optional explicit type mapping.

    Mapping keys use full XML element paths and Clark notation for namespaces.
    Attribute keys append '/@name'; unqualified attributes have no namespace.

    >>> from wcf.records import print_records
    >>> r = XMLParser.parse('<s:Envelope xmlns:s="urn:s"><b:Body xmlns:b="urn:b" /></s:Envelope>')
    >>> print_records(r)
    <s:Envelope xmlns:s="urn:s"><b:Body xmlns:b="urn:b"></b:Body></s:Envelope>
    """

    def __init__(self, type_overrides=None, dictionary_text=False):
        self.type_overrides = type_overrides or {}
        self.dictionary_text = dictionary_text
        self.reset()

    def reset(self):
        self.records = []
        self._stack = []
        self._namespace_stack = [{'xml': _XML_NS}]
        self._path = []
        self._data = []
        self._finalized = False
        self._parser = expat.ParserCreate()
        self._parser.StartElementHandler = self._on_start
        self._parser.EndElementHandler = self._on_end
        self._parser.CharacterDataHandler = self._on_data
        self._parser.CommentHandler = self._on_comment
        self._parser.StartDoctypeDeclHandler = self._on_doctype
        self._parser.ProcessingInstructionHandler = self._on_pi

    def _resolve_override(self, path):
        as_tuple = tuple(path)
        return self.type_overrides.get(as_tuple,
                                       self.type_overrides.get('/' + '/'.join(path)))

    def _value_record(self, value, path):
        if self.type_overrides:
            kind = self._resolve_override(path)
            if kind is not None:
                return _typed_text(value, kind)
        # DictionaryText is still a lexical string, not inferred numeric typing.
        # In sessionful MC-NBFSE, use strings already shared via a StringTable.
        if self.dictionary_text:
            index = inverted_dict.get(value)
            if index is not None:
                return DictionaryTextRecord(index)
        return _choose_chars_record(value)

    def _flush_text(self):
        if self._data:
            value = ''.join(self._data)
            self._data.clear()
            record = self._value_record(value, self._path)
            self._stack[-1].childs.append(record)

    def _parse_tag(self, tag):
        return _named_record(tag, _ELEMENT_RECORDS)

    def _parse_attr(self, name, value, ns):
        if name == 'xmlns' or name.startswith('xmlns:'):
            prefix = ncname(name[6:]) if name != 'xmlns' else None
            index = inverted_dict.get(value)
            if index is not None:
                return (ShortDictionaryXmlnsAttributeRecord(index) if prefix is None
                        else DictionaryXmlnsAttributeRecord(prefix, index))
            return (ShortXmlnsAttributeRecord(value) if prefix is None
                    else XmlnsAttributeRecord(prefix, value))
        if self.type_overrides:
            path = self._path + ['@' + _as_qname(name, ns, True)]
        else:
            path = None
            if ':' in name and name.partition(':')[0] not in ns:
                _as_qname(name, ns, True)  # WcfBinaryError: undeclared prefix
        record = self._value_record(value, path)
        return _named_record(name, _ATTRIBUTE_RECORDS, record)

    def _on_start(self, tag, attrs):
        if self._stack:
            self._flush_text()
        ns = self._namespace_stack[-1]
        copied = False
        for name, value in attrs.items():
            if name.startswith('xmlns'):
                if not copied:
                    # the scope of the parent is shared until one is declared
                    ns, copied = ns.copy(), True
                if name == 'xmlns':
                    ns[''] = value
                elif name.startswith('xmlns:'):
                    ns[name[6:]] = value
        if self.type_overrides:
            self._path.append(_as_qname(tag, ns))
        elif ':' in tag and tag.partition(':')[0] not in ns:
            _as_qname(tag, ns)  # WcfBinaryError: undeclared prefix
        element = self._parse_tag(tag)
        for name, value in attrs.items():
            element.attributes.append(self._parse_attr(name, value, ns))
        if self._stack:
            self._stack[-1].childs.append(element)
        else:
            self.records.append(element)
        self._stack.append(element)
        self._namespace_stack.append(ns)

    def _on_end(self, tag):
        self._flush_text()
        self._stack.pop()
        if self.type_overrides:
            self._path.pop()
        self._namespace_stack.pop()

    def _on_data(self, data):
        self._data.append(data)

    def _on_comment(self, comment):
        if self._stack:
            self._flush_text()
            self._stack[-1].childs.append(CommentRecord(comment))
        else:
            self.records.append(CommentRecord(comment))

    def _on_doctype(self, *args):
        raise WcfBinaryError('DOCTYPE is not supported in WCF Binary XML conversion')

    def _on_pi(self, target, data):
        raise WcfBinaryError('Processing instructions cannot be represented in MC-NBFX')

    def _parse(self, data, final):
        try:
            with binary_errors():  # e.g. binascii.Error of a base64 override
                self._parser.Parse(data, final)
        except expat.ExpatError as error:
            raise WcfBinaryError('Malformed XML: %s' % error) from None

    def feed(self, data):
        if self._finalized:
            raise WcfBinaryError('Parser already closed')
        self._parse(data, False)

    def close(self):
        if not self._finalized:
            self._parse(b'', True)
            self._finalized = True
        return self.records

    @classmethod
    def parse(cls, data, type_overrides=None, dictionary_text=False):
        """Parse XML input from bytes, str, or a file-like object."""
        if hasattr(data, 'read'):
            data = data.read()
        if not isinstance(data, (str, bytes)):
            raise TypeError('Expected XML text, bytes, or file-like object')
        p = cls(type_overrides=type_overrides, dictionary_text=dictionary_text)
        p.feed(data)
        return p.close()
