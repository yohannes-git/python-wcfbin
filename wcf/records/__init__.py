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
"""MC-NBFX records: the record classes, and documents to XML and bytes."""

import itertools
import sys

from wcf.errors import WcfBinaryError
from wcf.records import attributes, base, elements, text
from wcf.records.base import *
from wcf.records.text import *
from wcf.records.attributes import *
from wcf.records.elements import *
from wcf.records.base import (_ARRAY, _COMMENT, _ELEMENT, _TEXT, attribute_xml,
                              qualified_name, start_tag)
from wcf.xmltext import comment, escape_text

__all__ = (base.__all__ + text.__all__ + attributes.__all__ + elements.__all__ +
           ['render_xml', 'print_records', 'repr_records', 'dump_records'])

_END = object()


# text records whose str() never needs escaping (base64, floats, dates):
# exact classes, a subclass may render differently, and only those whose
# str() is made by this code whatever their value (a hand-made
# Int32TextRecord('<x/>') or DecimalTextRecord('<x/>') is escaped: they
# write str(value), and integers are short to scan anyway)
_SAFE_TEXT = frozenset((
    ZeroTextRecord, OneTextRecord, FalseTextRecord, TrueTextRecord,
    BoolTextRecord, FloatTextRecord, DoubleTextRecord, DatetimeTextRecord,
    UniqueIdTextRecord, UuidTextRecord, Bytes8TextRecord, Bytes16TextRecord,
    Bytes32TextRecord, EmptyTextRecord, TimeSpanTextRecord))


def _text_xml(record):
    if record.__class__ in _SAFE_TEXT:
        return str(record)
    return escape_text(str(record))


def render_xml(records):
    """Produce XML without introducing whitespace or altering text values.

    Iterative, so that the depth of a tree is not limited by the
    interpreter recursion limit.
    """
    parts = []
    append = parts.append
    stack = [(iter(records), None)]  # (siblings, end tag of their parent)
    while stack:
        siblings, end_tag = stack[-1]
        for r in siblings:
            kind = r._kind
            if kind is _TEXT and r.standalone:
                append(_text_xml(r))
            elif kind is _ELEMENT:
                name = qualified_name(r)
                if r.attributes:
                    append('<%s%s>' % (name, ''.join(map(attribute_xml, r.attributes))))
                else:
                    append('<%s>' % name)
                stack.append((iter(r.childs), '</%s>' % name))
                break
            elif kind is _ARRAY:
                tag = start_tag(r.element, r.attributes)
                end = '</%s>' % qualified_name(r.element)
                for value in r.data:
                    append(tag + _text_xml(value) + end)
            elif kind is _COMMENT:
                append(comment(r.comment))
            elif kind is _TEXT:
                raise WcfBinaryError('WCF EndListText without StartListText')
            else:
                raise WcfBinaryError('Cannot render record %s as XML' % type(r).__name__)
        else:
            stack.pop()
            if end_tag is not None:
                append(end_tag)
    return ''.join(parts)


def print_records(records, skip=0, fp=None, first_call=True):
    """Print the character-equivalent XML, without pretty-print whitespace.

    ``skip`` and ``first_call`` remain accepted for source compatibility
    (WcfPlugin.py); use render_xml().
    """
    if fp is None:
        fp = sys.stdout
    if records is not None:
        fp.write(render_xml(records))


def repr_records(records, skip=0):
    """Print the records of a tree, one per line, indented by depth
    (a debugging aid)."""
    stack = [(iter(records or ()), skip)]
    while stack:
        siblings, depth = stack[-1]
        r = next(siblings, _END)
        if r is _END:
            stack.pop()
            continue
        print(' ' * depth + str(r))
        if isinstance(r, Element):
            stack.append((iter(r.childs), depth + 1))


def dump_records(records):
    """Serialize a tree to MC-NBFX, without mutating its records.

    Closure style decoded from wire is retained: explicit EndElement (0x01)
    remains explicit, and TextWithEndElement remains implicit. Newly created
    trees use TextWithEndElement for their final text child by default.
    Iterative, like render_xml().
    """
    out = bytearray()
    stack = [(iter(records), None)]  # (siblings, closing record of their parent)
    while stack:
        siblings, closing = stack[-1]
        for record in siblings:
            out += record.to_bytes()
            if isinstance(record, Element):
                children = record.childs
                if (children and isinstance(children[-1], Text) and
                        children[-1].with_end_element and
                        record._wcf_closure != 'explicit'):
                    # the last text record is written in its *WithEndElement
                    # form when the element is closed (only the records of
                    # the open elements are kept)
                    stack.append((itertools.islice(children, len(children) - 1),
                                  children[-1].to_bytes()))
                else:
                    stack.append((iter(children), _END_ELEMENT))
                break
        else:
            stack.pop()
            if closing is _END_ELEMENT:
                out += closing
            elif closing is not None:
                # *TextWithEndElement: the type of the text record + 1,
                # without copying a large value
                out.append(closing[0] + 1)
                out += memoryview(closing)[1:]
    return bytes(out)


_END_ELEMENT = bytes((EndElementRecord.type,))
