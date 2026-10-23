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
"""Attribute records (MC-NBFX 2.2.2)."""

from wcf.datatypes import mbi31_bytes, read_mbi31, read_utf8, utf8_bytes
from wcf.dictionary import dictionary
from wcf.records.base import (Attribute, LetterPrefix, Record, _DictionaryName,
                              _NamedRecord, letter_records, read_attribute_text,
                              validate_attribute_text, validate_xml_name)

__all__ = ['ShortAttributeRecord', 'AttributeRecord',
           'ShortDictionaryAttributeRecord', 'DictionaryAttributeRecord',
           'PrefixAttributeRecord', 'PrefixDictionaryAttributeRecord',
           'ShortXmlnsAttributeRecord', 'XmlnsAttributeRecord',
           'ShortDictionaryXmlnsAttributeRecord',
           'DictionaryXmlnsAttributeRecord', 'PREFIX_ATTRIBUTES',
           'PREFIX_DICTIONARY_ATTRIBUTES']


class _AttributeRecord(_NamedRecord, Attribute):
    """An attribute: its names (see _NamedRecord) then its value, a text
    record."""
    _what = 'attribute'

    def __init__(self, *args):
        self._set_names(args[:-1])
        self.value = validate_attribute_text(args[-1]) if args else None

    def to_bytes(self):
        parts = self._head()
        parts.append(validate_attribute_text(self.value).to_bytes())
        return b''.join(parts)

    @classmethod
    def parse(cls, fp):
        names = cls._read_names(fp)
        return cls(*names, read_attribute_text(fp))


class ShortAttributeRecord(_AttributeRecord):
    """
    >>> from wcf.records import TrueTextRecord
    >>> ShortAttributeRecord('test', TrueTextRecord()).to_bytes()
    b'\\x04\\x04test\\x86'
    >>> from io import BytesIO
    >>> ShortAttributeRecord.parse(BytesIO(b'\\x04test\\x86')).value
    <TrueTextRecord(type=0x86)>
    """
    type = 0x04


class AttributeRecord(ShortAttributeRecord):
    """
    >>> from wcf.records import TrueTextRecord
    >>> AttributeRecord('x', 'test', TrueTextRecord()).to_bytes()
    b'\\x05\\x01x\\x04test\\x86'
    """
    type = 0x05
    _has_prefix = True


class ShortDictionaryAttributeRecord(_DictionaryName, _AttributeRecord):
    """
    >>> from wcf.records import TrueTextRecord
    >>> ShortDictionaryAttributeRecord(2, TrueTextRecord()).to_bytes()
    b'\\x06\\x02\\x86'
    >>> from io import BytesIO
    >>> str(ShortDictionaryAttributeRecord.parse(BytesIO(b'\\x0c\\x86')))
    'To="true"'
    """
    type = 0x06
    _by_index = True


class DictionaryAttributeRecord(ShortDictionaryAttributeRecord):
    """
    >>> from wcf.records import TrueTextRecord
    >>> DictionaryAttributeRecord('x', 2, TrueTextRecord()).to_bytes()
    b'\\x07\\x01x\\x02\\x86'
    """
    type = 0x07
    _has_prefix = True


class PrefixAttributeRecord(LetterPrefix, AttributeRecord):
    """Prefix a to z, from the record type.

    >>> from wcf.records import TrueTextRecord
    >>> PrefixAttributeARecord('name', TrueTextRecord()).to_bytes()
    b'&\\x04name\\x86'
    """
    type = None


class PrefixDictionaryAttributeRecord(LetterPrefix, DictionaryAttributeRecord):
    """Prefix a to z, from the record type.

    >>> from wcf.records import TrueTextRecord
    >>> PrefixDictionaryAttributeBRecord(2, TrueTextRecord()).to_bytes()
    b'\\r\\x02\\x86'
    >>> from io import BytesIO
    >>> str(PrefixDictionaryAttributeBRecord.parse(BytesIO(b'\\x02\\x86')))
    'b:Envelope="true"'
    """
    type = None


class ShortXmlnsAttributeRecord(Attribute):
    """A namespace declaration: a prefix (a String, ``_has_prefix``; None
    for the default namespace) and a namespace (a String, or a
    DictionaryString, ``_by_index``).

    >>> ShortXmlnsAttributeRecord('test').to_bytes()
    b'\\x08\\x04test'
    >>> from io import BytesIO
    >>> str(ShortXmlnsAttributeRecord.parse(BytesIO(b'\\x04test')))
    'xmlns="test"'
    """
    type = 0x08
    is_xmlns = True
    _has_prefix = False
    _by_index = False

    def __init__(self, *args):
        if len(args) != self._has_prefix + 1:
            raise TypeError('%s takes %d argument(s)'
                            % (type(self).__name__, self._has_prefix + 1))
        if self._has_prefix:
            self.prefix = validate_xml_name(args[0], 'xmlns prefix')
        if self._by_index:
            self.index = args[-1]
            dictionary[self.index]  # an unknown id is refused
        elif isinstance(args[-1], str):
            self.value = args[-1]
        else:
            raise TypeError('%s namespace must be str' % type(self).__name__)

    @property
    def namespace(self):
        return dictionary[self.index] if self._by_index else self.value

    @property
    def qname(self):
        return 'xmlns' if self.prefix is None else 'xmlns:' + self.prefix

    def to_bytes(self):
        out = bytearray((self.type,))
        if self._has_prefix:
            out += utf8_bytes(validate_xml_name(self.prefix, 'xmlns prefix'))
        if self._by_index:
            dictionary[self.index]  # never write an id unknown to the peer
            out += mbi31_bytes(self.index)
        else:
            out += utf8_bytes(self.value)
        return bytes(out)

    @classmethod
    def parse(cls, fp):
        args = [read_utf8(fp)] if cls._has_prefix else []
        args.append(read_mbi31(fp) if cls._by_index
                    else read_utf8(fp))
        return cls(*args)


class XmlnsAttributeRecord(ShortXmlnsAttributeRecord):
    """
    >>> XmlnsAttributeRecord('name', 'value').to_bytes()
    b'\\t\\x04name\\x05value'
    >>> from io import BytesIO
    >>> str(XmlnsAttributeRecord.parse(BytesIO(b'\\x04name\\x05value')))
    'xmlns:name="value"'
    """
    type = 0x09
    _has_prefix = True

    @property
    def name(self):
        """The prefix (former attribute name, kept for compatibility)."""
        return self.prefix


class ShortDictionaryXmlnsAttributeRecord(ShortXmlnsAttributeRecord):
    """
    >>> ShortDictionaryXmlnsAttributeRecord(6).to_bytes()
    b'\\n\\x06'
    >>> from io import BytesIO
    >>> str(ShortDictionaryXmlnsAttributeRecord.parse(BytesIO(b'\\x06')))
    'xmlns="http://www.w3.org/2005/08/addressing"'
    """
    type = 0x0A
    _by_index = True


class DictionaryXmlnsAttributeRecord(ShortDictionaryXmlnsAttributeRecord):
    """
    >>> DictionaryXmlnsAttributeRecord('a', 6).to_bytes()
    b'\\x0b\\x01a\\x06'
    >>> from io import BytesIO
    >>> str(DictionaryXmlnsAttributeRecord.parse(BytesIO(b'\\x01a\\x06')))
    'xmlns:a="http://www.w3.org/2005/08/addressing"'
    """
    type = 0x0B
    _has_prefix = True


Record.add_records((ShortAttributeRecord, AttributeRecord,
                    ShortDictionaryAttributeRecord, DictionaryAttributeRecord,
                    ShortXmlnsAttributeRecord, XmlnsAttributeRecord,
                    ShortDictionaryXmlnsAttributeRecord,
                    DictionaryXmlnsAttributeRecord))
PREFIX_DICTIONARY_ATTRIBUTES = letter_records(
    PrefixDictionaryAttributeRecord, 0x0C, 'PrefixDictionaryAttribute%sRecord', globals())
PREFIX_ATTRIBUTES = letter_records(
    PrefixAttributeRecord, 0x26, 'PrefixAttribute%sRecord', globals())
