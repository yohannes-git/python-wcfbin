"""XML text written from MC-NBFX records: names, escaping, comments.

MC-NBFX only requires names to be nonempty and not "xmlns", and lets
records carry characters that XML cannot; the XML written for them must
still have exactly the structure of the records (no markup injected by a
name or a comment) and represent the same characters once parsed again.
"""

import functools
import re

# XML 1.0 (fifth edition) NCName: a Name without ':'
_NAME_START = ('A-Z_a-z\xc0-\xd6\xd8-\xf6\xf8-˿Ͱ-ͽ'
               'Ϳ-῿‌‍⁰-↏Ⰰ-⿯'
               '、-퟿豈-﷏ﷰ-�\U00010000-\U000effff')
_NCNAME = re.compile('[%s][%s\\-.0-9\xb7̀-ͯ‿⁀]*'
                     % (_NAME_START, _NAME_START))
# characters outside the XML 1.0 Char production
_NOT_XML_CHAR = re.compile('[^\t\n\r\x20-퟿-�'
                           '\U00010000-\U0010ffff]')
_TEXT_ESCAPES = str.maketrans({'&': '&amp;', '<': '&lt;', '>': '&gt;',
                               '\r': '&#13;'})
_ATTRIBUTE_ESCAPES = str.maketrans({'&': '&amp;', '<': '&lt;', '>': '&gt;',
                                    '"': '&quot;', '\t': '&#9;',
                                    '\n': '&#10;', '\r': '&#13;'})


@functools.lru_cache(maxsize=1024)
def ncname(name):
    """A name or prefix, ValueError if it is not an XML NCName.

    >>> ncname('Envelope')
    'Envelope'
    >>> ncname('a b="c"')
    Traceback (most recent call last):
    ...
    ValueError: MC-NBFX name 'a b="c"' cannot be represented in XML
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


def escape_text(value):
    """Element content.

    >>> escape_text('a<b>&\\r\\x00')
    'a&lt;b&gt;&amp;&#13;&#0;'
    """
    return _escape(value, _TEXT_ESCAPES)


def escape_attribute(value):
    """An attribute value, between double quotes.

    >>> escape_attribute('"\\t\\n')
    '&quot;&#9;&#10;'
    """
    return _escape(value, _ATTRIBUTE_ESCAPES)


def comment(text):
    """A comment, ValueError if XML cannot carry it.

    >>> comment('a-b')
    '<!--a-b-->'
    """
    # XML comments cannot contain "--" nor end with "-"
    if '--' in text or text.endswith('-'):
        raise ValueError('MC-NBFX comment %r cannot be represented in XML'
                         % (text,))
    return '<!--%s-->' % _escape(text, {})
