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
from wcf.records.base import qualified_name, start_tag
from wcf.xmltext import comment, escape_text

__all__ = (base.__all__ + text.__all__ + attributes.__all__ + elements.__all__ +
           ['render_xml', 'print_records', 'repr_records', 'dump_records'])

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
            tag = start_tag(r.element, r.attributes)
            end = '</%s>' % qualified_name(r.element)
            for value in r.data:
                parts.append(tag + escape_text(str(value)) + end)
        elif isinstance(r, Element):
            parts.append(start_tag(r))
            stack.append((iter(r.childs), '</%s>' % qualified_name(r)))
        elif isinstance(r, CommentRecord):
            parts.append(comment(r.comment))
        elif isinstance(r, Text) and r.standalone:
            parts.append(escape_text(str(r)))
        elif isinstance(r, Text):
            raise WcfBinaryError('WCF EndListText without StartListText')
        else:
            raise WcfBinaryError('Cannot render record %s as XML' % type(r).__name__)
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
    stack = [(iter(records), None)]  # (siblings, bytes closing their parent)
    while stack:
        siblings, closing = stack[-1]
        record = next(siblings, _END)
        if record is _END:
            stack.pop()
            if closing is not None:
                out.extend(closing)
        elif isinstance(record, Element):
            out.extend(record.to_bytes())
            children = record.childs
            if (children and isinstance(children[-1], Text) and
                    children[-1].with_end_element and
                    record._wcf_closure != 'explicit'):
                # the last text record becomes its *WithEndElement form
                value = children[-1].to_bytes()
                stack.append((itertools.islice(children, len(children) - 1),
                              bytes((value[0] + 1,)) + value[1:]))
            else:
                stack.append((iter(children), bytes((EndElementRecord.type,))))
        else:
            out.extend(record.to_bytes())
    return bytes(out)
