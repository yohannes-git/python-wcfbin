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
"""Element records (MC-NBFX 2.2.1)."""

from wcf.records.base import (Element, LetterPrefix, Record, _DictionaryName,
                              _NamedRecord, letter_records)

__all__ = ['ShortElementRecord', 'ElementRecord', 'ShortDictionaryElementRecord',
           'DictionaryElementRecord', 'PrefixElementRecord',
           'PrefixDictionaryElementRecord', 'PREFIX_ELEMENTS',
           'PREFIX_DICTIONARY_ELEMENTS']


class _ElementRecord(_NamedRecord, Element):
    """An element: its names (see _NamedRecord) then its attributes."""
    _what = 'element'

    def __init__(self, *names):
        self._set_names(names)
        self.attributes = []
        self.childs = []

    def to_bytes(self):
        parts = self._head()
        parts.extend([a.to_bytes() for a in self.attributes])
        return b''.join(parts)

    @classmethod
    def parse(cls, fp):
        return cls(*cls._read_names(fp))


class ShortElementRecord(_ElementRecord):
    """
    >>> ShortElementRecord('Envelope').to_bytes()
    b'@\\x08Envelope'
    >>> from io import BytesIO
    >>> str(ShortElementRecord.parse(BytesIO(b'\\x08Envelope')))
    '<Envelope>'
    """
    type = 0x40


class ElementRecord(ShortElementRecord):
    """
    >>> ElementRecord('x', 'Envelope').to_bytes()
    b'A\\x01x\\x08Envelope'
    >>> from io import BytesIO
    >>> str(ElementRecord.parse(BytesIO(b'\\x01x\\x08Envelope')))
    '<x:Envelope>'
    """
    type = 0x41
    _has_prefix = True


class ShortDictionaryElementRecord(_DictionaryName, _ElementRecord):
    """
    >>> ShortDictionaryElementRecord(2).to_bytes()
    b'B\\x02'
    >>> from io import BytesIO
    >>> str(ShortDictionaryElementRecord.parse(BytesIO(b'\\x02')))
    '<Envelope>'
    """
    type = 0x42
    _by_index = True


class DictionaryElementRecord(ShortDictionaryElementRecord):
    """
    >>> DictionaryElementRecord('x', 2).to_bytes()
    b'C\\x01x\\x02'
    >>> from io import BytesIO
    >>> str(DictionaryElementRecord.parse(BytesIO(b'\\x01x\\x02')))
    '<x:Envelope>'
    """
    type = 0x43
    _has_prefix = True


class PrefixElementRecord(LetterPrefix, ElementRecord):
    """Prefix a to z, from the record type.

    >>> PrefixElementARecord('test').to_bytes()
    b'^\\x04test'
    >>> from io import BytesIO
    >>> str(PrefixElementARecord.parse(BytesIO(b'\\x04test')))
    '<a:test>'
    """
    type = None


class PrefixDictionaryElementRecord(LetterPrefix, DictionaryElementRecord):
    """Prefix a to z, from the record type.

    >>> PrefixDictionaryElementARecord(2).to_bytes()
    b'D\\x02'
    >>> from io import BytesIO
    >>> str(PrefixDictionaryElementSRecord.parse(BytesIO(b'\\x02')))
    '<s:Envelope>'
    """
    type = None


Record.add_records((ShortElementRecord, ElementRecord,
                    ShortDictionaryElementRecord, DictionaryElementRecord))
PREFIX_DICTIONARY_ELEMENTS = letter_records(
    PrefixDictionaryElementRecord, 0x44, 'PrefixDictionaryElement%sRecord', globals())
PREFIX_ELEMENTS = letter_records(
    PrefixElementRecord, 0x5E, 'PrefixElement%sRecord', globals())
