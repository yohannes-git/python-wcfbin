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

import sys
import logging

log = logging.getLogger(__name__)

from wcf.records.base import *
from wcf.records.text import *
from wcf.records.attributes import *
from wcf.records.elements import *

import functools
import itertools
import re

from wcf.dictionary import dictionary


# XML 1.0 (fifth edition) NCName: a Name without ':'
_NAME_START = ('A-Z_a-z\xc0-\xd6\xd8-\xf6\xf8-\u02ff\u0370-\u037d'
               '\u037f-\u1fff\u200c\u200d\u2070-\u218f\u2c00-\u2fef'
               '\u3001-\ud7ff\uf900-\ufdcf\ufdf0-\ufffd\U00010000-\U000effff')
_NCNAME = re.compile('[%s][%s\\-.0-9\xb7\u0300-\u036f\u203f\u2040]*'
                     % (_NAME_START, _NAME_START))
# characters outside the XML 1.0 Char production
_NOT_XML_CHAR = re.compile('[^\t\n\r\x20-\ud7ff\ue000-\ufffd'
                           '\U00010000-\U0010ffff]')
_TEXT_ESCAPES = str.maketrans({'&': '&amp;', '<': '&lt;', '>': '&gt;',
                               '\r': '&#13;'})
_ATTRIBUTE_ESCAPES = str.maketrans({'&': '&amp;', '<': '&lt;', '>': '&gt;',
                                    '"': '&quot;', '\t': '&#9;',
                                    '\n': '&#10;', '\r': '&#13;'})


@functools.lru_cache(maxsize=1024)
def _xml_name(name):
    """A name or prefix, refused when it cannot be written as XML.

    MC-NBFX only requires names to be nonempty and not "xmlns"; a name
    that is not an NCName (e.g. 'a b="c"') would change the structure
    of the rendered document.
    """
    if not _NCNAME.fullmatch(name):
        raise ValueError('MC-NBFX name %r cannot be represented in XML'
                         % (name,))
    return name


def _escape(value, table):
    """Escape a value as MC-NBFX 2.2.3.13.1 interprets it.

    Markup characters become entity references and characters that are
    not legal in XML become "&#digits;". Line ends (and tabs and line
    feeds in attributes) are written as character references too, so
    that an XML parser's end-of-line and attribute-value normalization
    does not change the characters the record represents.
    """
    value = value.translate(table)
    if _NOT_XML_CHAR.search(value):
        value = _NOT_XML_CHAR.sub(lambda m: '&#%d;' % ord(m.group()), value)
    return value


def _name(obj):
    name = _xml_name(dictionary[obj.index] if not hasattr(obj, 'name')
                     else obj.name)
    if hasattr(obj, 'prefix'):
        return '%s:%s' % (_xml_name(obj.prefix), name)
    return name


def _text(record):
    return _escape(str(record), _TEXT_ESCAPES)


def _attr(record):
    if isinstance(record, (ShortXmlnsAttributeRecord,
                           ShortDictionaryXmlnsAttributeRecord)):
        name = 'xmlns'
        value = dictionary[record.index] if hasattr(record, 'index') else record.value
    elif isinstance(record, (XmlnsAttributeRecord,
                             DictionaryXmlnsAttributeRecord)):
        prefix = record.name if hasattr(record, 'name') else record.prefix
        name = 'xmlns:' + _xml_name(prefix)
        value = dictionary[record.index] if hasattr(record, 'index') else record.value
    else:
        name = _name(record)
        value = str(record.value)
    return ' %s="%s"' % (name, _escape(value, _ATTRIBUTE_ESCAPES))


def _comment(record):
    # XML comments cannot contain "--" nor end with "-"
    if '--' in record.comment or record.comment.endswith('-'):
        raise ValueError('MC-NBFX comment %r cannot be represented in XML'
                         % (record.comment,))
    return '<!--%s-->' % _escape(record.comment, {})


_END = object()


def render_xml(records):
    """Produce XML without introducing whitespace or altering text values.

    Iterative, so that the depth of a tree is not limited by the
    interpreter recursion limit.
    """
    parts = []
    stack = [(iter(records), None)]  # (siblings, end tag of their parent)
    while stack:
        siblings, end_tag = stack[-1]
        r = next(siblings, _END)
        if r is _END:
            stack.pop()
            if end_tag is not None:
                parts.append(end_tag)
        elif isinstance(r, ArrayRecord):
            name = _name(r.element)
            attrs = ''.join(_attr(a) for a in r.element.attributes + r.attributes)
            for value in r.data:
                parts.append('<%s%s>%s</%s>' % (name, attrs, _text(value), name))
        elif isinstance(r, Element):
            if isinstance(r, EndElementRecord):
                raise ValueError('Unexpected EndElement in record tree')
            name = _name(r)
            parts.append('<%s%s>' % (
                name, ''.join(_attr(a) for a in r.attributes)))
            stack.append((iter(r.childs), '</%s>' % name))
        elif isinstance(r, CommentRecord):
            parts.append(_comment(r))
        elif isinstance(r, EndListTextRecord):
            raise ValueError('WCF EndListText without StartListText')
        elif isinstance(r, Text):
            parts.append(_text(r))
        else:
            raise ValueError('Cannot render record %s as XML' % type(r).__name__)
    return ''.join(parts)


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
    Iterative, like render_xml().
    """
    out = bytearray()
    stack = [(iter(records), None)]  # (siblings, bytes closing their parent)
    while stack:
        siblings, closing = stack[-1]
        record = next(siblings, _END)
        if record is _END:
            stack.pop()
            if closing is not None:
                out.extend(closing)
        elif isinstance(record, Element) and not isinstance(record, EndElementRecord):
            out.extend(record.to_bytes())
            children = getattr(record, 'childs', [])
            implicit = (bool(children) and isinstance(children[-1], Text) and
                        children[-1].type not in (0xA4, 0xA6) and
                        getattr(record, '_wcf_closure', None) != 'explicit')
            if implicit:
                # the last text record becomes its *WithEndElement form
                value = children[-1].to_bytes()
                stack.append((itertools.islice(children, len(children) - 1),
                              bytes((value[0] + 1,)) + value[1:]))
            else:
                stack.append((iter(children), bytes((EndElementRecord.type,))))
        else:
            out.extend(record.to_bytes())
    return bytes(out)
