"""XML -> MC-NBFX record tree.

Ordinary XML supplies *lexical text*, not WCF wire types.  By default every
text or attribute value is written as a UTF-8 Chars record; optional explicit
type overrides are keyed by an XML namespace-aware path.
"""


import base64
import io
import re
from xml.parsers import expat

from wcf.dictionary import inverted_dict
from wcf.xmltext import ncname
from wcf.records import (
    Record, ShortElementRecord, ElementRecord, ShortDictionaryElementRecord,
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
    dump_records,
)
from wcf.datatypes import Decimal
from wcf.records import elements, attributes


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
            raise ValueError('Undeclared XML namespace prefix: %s' % prefix)
        uri = ns[prefix]
    else:
        local = name
        uri = '' if is_attribute else ns.get('', '')
    return '{%s}%s' % (uri, local) if uri else local


def _smallest_record(classes, value, length):
    """The record of ``classes`` with the smallest length field that can
    hold ``length`` bytes."""
    for record in classes:
        if length <= record.max_length():
            return record(value)
    raise ValueError('%s too long (%d bytes)' % (classes[-1].__name__, length))


def _choose_chars_record(data):
    return _smallest_record((Chars8TextRecord, Chars16TextRecord,
                             Chars32TextRecord), data, len(data.encode('utf-8')))


def _choose_bytes_record(value):
    return _smallest_record((Bytes8TextRecord, Bytes16TextRecord,
                             Bytes32TextRecord), value, len(value))


def _typed_text(value, kind):
    """Build a typed record only when the caller knows the expected type."""
    kind = kind.lower()
    if kind in ('text', 'string', 'chars'):
        return _choose_chars_record(value)
    stripped = value.strip()
    if kind in _INT_TYPES:
        record, minval, maxval = _INT_TYPES[kind]
        if not re.fullmatch(r'[+-]?[0-9]+', stripped):
            raise ValueError('Invalid %s value %r' % (kind, value))
        n = int(stripped)
        if not minval <= n <= maxval:
            raise ValueError('%s out of range: %r' % (kind, value))
        return record(n)
    if kind in ('bool', 'boolean'):
        if stripped in ('true', '1'):
            return BoolTextRecord(True)
        if stripped in ('false', '0'):
            return BoolTextRecord(False)
        raise ValueError('Invalid boolean literal %r' % value)
    if kind in ('float', 'double'):
        if stripped in ('INF', '+INF'):
            n = float('inf')
        elif stripped == '-INF':
            n = float('-inf')
        elif stripped == 'NaN':
            n = float('nan')
        elif re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?', stripped):
            n = float(stripped)
        else:
            raise ValueError('Invalid floating-point literal %r' % value)
        return FloatTextRecord(n) if kind == 'float' else DoubleTextRecord(n)
    if kind == 'decimal':
        return DecimalTextRecord(Decimal.from_string(stripped))
    if kind == 'uuid':
        return UuidTextRecord(stripped)
    if kind == 'uniqueid':
        return UniqueIdTextRecord(stripped)
    if kind in ('base64', 'bytes'):
        # Whitespace is permitted in XML Schema base64 lexical values.
        clean = ''.join(stripped.split())
        return _choose_bytes_record(base64.b64decode(clean, validate=True))
    raise ValueError('Unsupported explicit WCF type %r' % kind)


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
        kind = self._resolve_override(path)
        if kind is not None:
            return _typed_text(value, kind)
        # DictionaryText is still a lexical string, not inferred numeric typing.
        # In sessionful MC-NBFSE, use strings already shared via a StringTable.
        if self.dictionary_text and value in inverted_dict:
            return DictionaryTextRecord(inverted_dict[value])
        return _choose_chars_record(value)

    def _flush_text(self):
        if self._data:
            value = ''.join(self._data)
            self._data.clear()
            record = self._value_record(value, self._path)
            self._stack[-1].childs.append(record)

    def _parse_tag(self, tag):
        if ':' in tag:
            prefix, name = tag.split(':', 1)
            ncname(prefix)
            ncname(name)
            if len(prefix) == 1 and 'a' <= prefix <= 'z':
                if name in inverted_dict:
                    cls = getattr(elements, 'PrefixDictionaryElement%sRecord' % prefix.upper())
                    return cls(inverted_dict[name])
                cls = getattr(elements, 'PrefixElement%sRecord' % prefix.upper())
                return cls(name)
            if name in inverted_dict:
                return DictionaryElementRecord(prefix, inverted_dict[name])
            return ElementRecord(prefix, name)
        if ncname(tag) in inverted_dict:
            return ShortDictionaryElementRecord(inverted_dict[tag])
        return ShortElementRecord(tag)

    def _parse_attr(self, name, value, ns):
        if name == 'xmlns':
            if value in inverted_dict:
                return ShortDictionaryXmlnsAttributeRecord(inverted_dict[value])
            return ShortXmlnsAttributeRecord(value)
        if name.startswith('xmlns:'):
            prefix = ncname(name[6:])
            if value in inverted_dict:
                return DictionaryXmlnsAttributeRecord(prefix, inverted_dict[value])
            return XmlnsAttributeRecord(prefix, value)

        record = self._value_record(value, self._path + ['@' + _as_qname(name, ns, True)])
        if ':' in name:
            prefix, local = name.split(':', 1)
            ncname(prefix)
            ncname(local)
            if len(prefix) == 1 and 'a' <= prefix <= 'z':
                if local in inverted_dict:
                    cls = getattr(attributes, 'PrefixDictionaryAttribute%sRecord' % prefix.upper())
                    return cls(inverted_dict[local], record)
                cls = getattr(attributes, 'PrefixAttribute%sRecord' % prefix.upper())
                return cls(local, record)
            if local in inverted_dict:
                return DictionaryAttributeRecord(prefix, inverted_dict[local], record)
            return AttributeRecord(prefix, local, record)
        if ncname(name) in inverted_dict:
            return ShortDictionaryAttributeRecord(inverted_dict[name], record)
        return ShortAttributeRecord(name, record)

    def _on_start(self, tag, attrs):
        if self._stack:
            self._flush_text()
        ns = self._namespace_stack[-1].copy()
        for name, value in attrs.items():
            if name == 'xmlns':
                ns[''] = value
            elif name.startswith('xmlns:'):
                ns[name[6:]] = value
        self._path.append(_as_qname(tag, ns))
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
        raise ValueError('DOCTYPE is not supported in WCF Binary XML conversion')

    def _on_pi(self, target, data):
        raise ValueError('Processing instructions cannot be represented in MC-NBFX')

    def _parse(self, data, final):
        try:
            self._parser.Parse(data, final)
        except expat.ExpatError as error:
            raise ValueError('Malformed XML: %s' % error) from None

    def feed(self, data):
        if self._finalized:
            raise ValueError('Parser already closed')
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


if __name__ == '__main__':
    import sys
    p = XMLParser.parse(sys.stdin.buffer.read())
    sys.stdout.buffer.write(dump_records(p))
