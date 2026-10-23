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
from __future__ import absolute_import, print_function, unicode_literals

from builtins import str
import sys
import logging

log = logging.getLogger(__name__)

from wcf.records.base import *
from wcf.records.text import *
from wcf.records.attributes import *
from wcf.records.elements import *

from xml.sax.saxutils import escape
from wcf.dictionary import dictionary


def _name(obj):
    name = dictionary[obj.index] if not hasattr(obj, 'name') else obj.name
    return '%s:%s' % (obj.prefix, name) if hasattr(obj, 'prefix') else name


def _text(record):
    # Char records have a raw lexical value. __str__ of Chars* already
    # escapes it, so calling escape(str(record)) would double-escape.
    if isinstance(record, (Chars8TextRecord, UnicodeChars8TextRecord)):
        return record.value
    return str(record)


def _attr(record):
    if isinstance(record, (ShortXmlnsAttributeRecord,
                           ShortDictionaryXmlnsAttributeRecord)):
        name = 'xmlns'
        value = dictionary[record.index] if hasattr(record, 'index') else record.value
    elif isinstance(record, (XmlnsAttributeRecord,
                             DictionaryXmlnsAttributeRecord)):
        prefix = record.name if hasattr(record, 'name') else record.prefix
        name = 'xmlns:' + prefix
        value = dictionary[record.index] if hasattr(record, 'index') else record.value
    else:
        name = _name(record)
        value = _text(record.value)
    # XML attribute whitespace must be preserved using character references.
    escaped = escape(value, {'"': '&quot;', '\t': '&#x9;',
                             '\r': '&#xD;', '\n': '&#xA;'})
    return ' %s="%s"' % (name, escaped)


def _render_nodes(records):
    parts = []
    records = list(records)
    i = 0
    while i < len(records):
        r = records[i]
        if isinstance(r, ArrayRecord):
            name = _name(r.element)
            attrs = ''.join(_attr(a) for a in r.element.attributes + r.attributes)
            for value in r.data:
                parts.append('<%s%s>%s</%s>' % (
                    name, attrs, escape(_text(value)), name))
        elif isinstance(r, Element):
            if isinstance(r, EndElementRecord):
                raise ValueError('Unexpected EndElement in record tree')
            name = _name(r)
            parts.append('<%s%s>' % (
                name, ''.join(_attr(a) for a in r.attributes)))
            parts.append(_render_nodes(r.childs))
            parts.append('</%s>' % name)
        elif isinstance(r, CommentRecord):
            parts.append('<!--%s-->' % r.comment)
        elif isinstance(r, StartListTextRecord):
            parts.append(escape(' '.join(_text(value) for value in r.values)))
        elif isinstance(r, EndListTextRecord):
            raise ValueError('WCF EndListText without StartListText')
        elif isinstance(r, Text):
            parts.append(escape(_text(r)))
        else:
            raise ValueError('Cannot render record %s as XML' % type(r).__name__)
        i += 1
    return ''.join(parts)


def render_xml(records):
    """Produce XML without introducing whitespace or altering text values."""
    return _render_nodes(records)


def print_records(records, skip=0, fp=None, first_call=True):
    """Print the character-equivalent XML, without pretty-print whitespace.

    ``skip`` and ``first_call`` remain accepted for source compatibility.
    """
    if fp is None:
        fp = sys.stdout
    if records is not None:
        fp.write(render_xml(records))


def repr_records(records, skip=0):
    if records is None:
        return
    for r in records:
        print(' ' * skip + str(r))
        if hasattr(r, 'childs'):
            repr_records(r.childs, skip + 1)


def dump_records(records):
    """Serialize a tree to MC-NBFX, without mutating its records.

    Closure style decoded from wire is retained: explicit EndElement (0x01)
    remains explicit, and TextWithEndElement remains implicit. Newly created
    trees use TextWithEndElement for their final text child by default.
    """
    out = bytearray()
    for record in records:
        if isinstance(record, Element) and not isinstance(record, EndElementRecord):
            out.extend(record.to_bytes())
            children = getattr(record, 'childs', [])
            implicit = (bool(children) and isinstance(children[-1], Text) and
                        children[-1].type not in (0xA4, 0xA6) and
                        getattr(record, '_wcf_closure', None) != 'explicit')
            if implicit:
                out.extend(dump_records(children[:-1]))
                last = children[-1]
                value = last.to_bytes()
                out.append(last.type + 1)
                out.extend(value[1:])
            else:
                out.extend(dump_records(children))
                out.append(EndElementRecord.type)
        else:
            out.extend(record.to_bytes())
    return bytes(out)
