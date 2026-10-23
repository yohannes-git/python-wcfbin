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


"""Text records (MC-NBFX 2.2.3)."""

import base64
import datetime
import decimal
import math
import struct
import time
import uuid

from wcf.errors import WcfBinaryError
from wcf.datatypes import Decimal, mbi31_bytes, read_exact, read_mbi31, read_struct
from wcf.dictionary import dictionary
from wcf.records.base import Record, Text, charge

__all__ = ['ZeroTextRecord', 'OneTextRecord', 'FalseTextRecord',
           'TrueTextRecord', 'Int8TextRecord', 'Int16TextRecord',
           'Int32TextRecord', 'Int64TextRecord', 'UInt64TextRecord',
           'BoolTextRecord', 'UnicodeChars8TextRecord',
           'UnicodeChars16TextRecord', 'UnicodeChars32TextRecord',
           'QNameDictionaryTextRecord', 'FloatTextRecord', 'DoubleTextRecord',
           'DecimalTextRecord', 'DatetimeTextRecord', 'Chars8TextRecord',
           'Chars16TextRecord', 'Chars32TextRecord', 'UniqueIdTextRecord',
           'UuidTextRecord', 'Bytes8TextRecord', 'Bytes16TextRecord',
           'Bytes32TextRecord', 'StartListTextRecord', 'EndListTextRecord',
           'EmptyTextRecord', 'TimeSpanTextRecord', 'DictionaryTextRecord']

TICKS_PER_SECOND = 10000000          # 100 ns
TICKS_PER_DAY = 86400 * TICKS_PER_SECOND
MAX_DATETIME_TICKS = 3155378976000000000  # 10000-01-01T00:00:00
TICKS_CEILING = 1 << 62  # the 62-bit DateTime field
_UNIX_EPOCH_TICKS = 621355968000000000  # 1970-01-01T00:00:00


def _fraction(ticks):
    """The ".fffffff" fraction of a second, without trailing zeros."""
    return '.' + ('%07d' % ticks).rstrip('0') if ticks else ''


def _shortest_ieee754_text(value, single_precision):
    """MC-NBFX 2.2.3.9/10: shortest round-trippable decimal representation.

    float32 has at most nine significant decimal digits; float64 has at most
    seventeen. Compare the *bits* of each round-trip candidate so that this
    does not accidentally display the expanded float64 approximation of a
    decoded float32. Do not infer a type from untyped XML input here.
    """
    code = '<f' if single_precision else '<d'
    maximum_digits = 9 if single_precision else 17
    original = struct.pack(code, value)
    rounded = struct.unpack(code, original)[0]
    if math.isnan(rounded):
        return 'NaN'
    if math.isinf(rounded):
        return '-INF' if rounded < 0 else 'INF'
    if rounded == 0:
        return '-0' if math.copysign(1.0, rounded) < 0 else '0'

    for digits in range(1, maximum_digits + 1):
        candidate = format(rounded, '.%dg' % digits)
        try:
            if struct.pack(code, float(candidate)) == original:
                break
        except (OverflowError, ValueError):
            continue
    else:
        raise WcfBinaryError('Cannot render MC-NBFX floating-point value')

    # Choose ordinary decimal only when the point falls within the range of
    # significant digits, or just before it ("0.5": "except when a decimal
    # point is the first character, in which case a single zero MUST
    # precede the decimal point"). Outside that range MC-NBFX requires
    # E[+-]exponent: 100 is "1E+2" (.NET would write "100", the text of
    # 2.2.3.9/2.2.3.10 is followed, no example covers this case).
    as_decimal = decimal.Decimal(candidate)
    negative = as_decimal.is_signed()
    sign, digit_tuple, exponent = as_decimal.as_tuple()
    figures = ''.join(map(str, digit_tuple))
    decimal_position = len(figures) + exponent
    if 0 <= decimal_position <= len(figures):
        return format(as_decimal, 'f')

    mantissa = figures[:1]
    if len(figures) > 1:
        mantissa += '.' + figures[1:]
    return ('-' if negative else '') + mantissa + 'E%+d' % (decimal_position - 1)



class _FixedSizeText(Text):
    """A text record holding one fixed-size little-endian value
    (``_format``), rendered with str() unless the class says otherwise."""
    _format = None
    _value_types = (int,)  # bool excluded
    _array_unpack = True  # False in a subclass with its own parse()

    def __init__(self, value):
        if value.__class__ is bool or not isinstance(value, self._value_types):
            raise TypeError('%s value must be %s, not %s' % (
                type(self).__name__, ' or '.join(t.__name__ for t in self._value_types),
                type(value).__name__))
        self.value = value

    def to_bytes(self):
        """
        >>> Int8TextRecord(42).to_bytes()
        b'\\x88*'
        >>> Int16TextRecord(1337).to_bytes()
        b'\\x8a9\\x05'
        >>> UInt64TextRecord(1337).to_bytes()
        b'\\xb29\\x05\\x00\\x00\\x00\\x00\\x00\\x00'
        >>> Int8TextRecord(128).to_bytes()  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        wcf.errors.WcfBinaryError: Int8TextRecord: ...
        """
        try:
            value = struct.pack(self._format, self.value)
        except (struct.error, OverflowError) as error:
            raise WcfBinaryError('%s: %s' % (type(self).__name__, error)) from None
        return struct.pack('<B', self.type) + value

    def __str__(self):
        """
        >>> str(Int32TextRecord(-2147483648))
        '-2147483648'
        """
        return str(self.value)

    @classmethod
    def parse(cls, fp):
        """
        >>> from io import BytesIO
        >>> Int8TextRecord.parse(BytesIO(b'\\xff')).value
        -1
        >>> UInt64TextRecord.parse(BytesIO(b'\\xff' * 8)).value
        18446744073709551615
        """
        return cls(read_struct(fp, cls._format))


class _LengthPrefixedText(Text):
    """Chars*, Bytes* and UnicodeChars* text: a length (``_length_format``)
    then the encoded value. Chars32Text and Bytes32Text (MC-NBFX
    2.2.3.15, 2.2.3.18) require a positive length (``_positive``)."""
    _length_format = '<B'
    _positive = False

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return self.value

    def _encode(self):
        return self.value.encode('utf-8')

    @classmethod
    def _decode(cls, data):
        return data.decode('utf-8')

    @classmethod
    def max_length(cls):
        """The longest value (in bytes) the length field can hold.

        >>> Chars8TextRecord.max_length(), Bytes32TextRecord.max_length()
        (255, 2147483647)
        """
        bits = 8 * struct.calcsize(cls._length_format)
        signed = cls._length_format[-1].islower()
        return (1 << (bits - signed)) - 1

    def to_bytes(self):
        data = self._encode()
        if self._positive and not data:
            raise WcfBinaryError('%s length must be positive' % type(self).__name__)
        try:
            length = struct.pack(self._length_format, len(data))
        except struct.error:
            raise WcfBinaryError('%s too long (%d bytes)'
                             % (type(self).__name__, len(data))) from None
        return b''.join((bytes((self.type,)), length, data))  # one copy

    @classmethod
    def parse(cls, fp):
        length = read_struct(fp, cls._length_format)
        if length < 0 or (cls._positive and length == 0):
            raise WcfBinaryError('%s length must be %s' % (
                cls.__name__, 'positive' if cls._positive else 'non-negative'))
        return cls(cls._decode(read_exact(fp, length)))


class _ConstantText(Text):
    """A text record without fields that stands for fixed characters."""
    text = None

    def __str__(self):
        return self.text


class ZeroTextRecord(_ConstantText):
    type = 0x80
    xml_safe = True
    text = '0'
    max_chars = 1


class OneTextRecord(_ConstantText):
    type = 0x82
    xml_safe = True
    text = '1'
    max_chars = 1


class FalseTextRecord(_ConstantText):
    type = 0x84
    xml_safe = True
    text = 'false'
    max_chars = 5


class TrueTextRecord(_ConstantText):
    type = 0x86
    xml_safe = True
    text = 'true'
    max_chars = 4


class Int8TextRecord(_FixedSizeText):
    type = 0x88
    max_chars = 4
    _format = '<b'


class Int16TextRecord(_FixedSizeText):
    type = 0x8A
    max_chars = 6
    _format = '<h'


class Int32TextRecord(_FixedSizeText):
    type = 0x8C
    max_chars = 11
    _format = '<i'


class Int64TextRecord(_FixedSizeText):
    type = 0x8E
    max_chars = 20
    _format = '<q'


class UInt64TextRecord(_FixedSizeText):
    type = 0xB2
    max_chars = 20
    _format = '<Q'


class BoolTextRecord(Text):
    type = 0xB4
    xml_safe = True
    max_chars = 5

    def __init__(self, value):
        if value.__class__ is not bool:
            raise TypeError('BoolTextRecord value must be bool, not %s'
                            % type(value).__name__)
        self.value = value

    def to_bytes(self):
        r"""
        >>> BoolTextRecord(True).to_bytes()
        b'\xb4\x01'
        >>> BoolTextRecord(False).to_bytes()
        b'\xb4\x00'
        """
        return bytes(struct.pack(b'<B', self.type) +
                     struct.pack(b'<B', 1 if self.value else 0))

    def __str__(self):
        r"""
        >>> str(BoolTextRecord(True))
        'true'
        """
        return 'true' if self.value else 'false'

    @classmethod
    def parse(cls, fp):
        r"""
        >>> from io import BytesIO
        >>> fp = BytesIO(b'\x01')
        >>> BoolTextRecord.parse(fp).value
        True
        """
        byte = read_struct(fp, '<B')
        if byte not in (0, 1):
            raise WcfBinaryError('Invalid BoolText value %d' % byte)
        return cls(bool(byte))


class _Utf8Text(_LengthPrefixedText):
    """UTF-8 text (MC-NBFX 2.2.3.13 to 2.2.3.15).

    >>> Chars8TextRecord('abc').to_bytes()
    b'\\x98\\x03abc'
    >>> Chars16TextRecord('abc').to_bytes()
    b'\\x9a\\x03\\x00abc'
    >>> Chars32TextRecord('abc').to_bytes()
    b'\\x9c\\x03\\x00\\x00\\x00abc'
    >>> from io import BytesIO
    >>> str(Chars16TextRecord.parse(BytesIO(b'\\x04\\x00test')))
    'test'

    str() is the characters, unescaped like every other text record (the
    XML escaping is done by render_xml()):

    >>> str(Chars8TextRecord('a<b>&'))
    'a<b>&'
    """

    def __init__(self, value):
        if not isinstance(value, str):
            raise TypeError('%s value must be str, not %s'
                            % (type(self).__name__, type(value).__name__))
        super().__init__(value)


class _Utf16Text(_Utf8Text):
    """UTF-16LE text (MC-NBFX 2.2.3.27 to 2.2.3.29).

    >>> UnicodeChars8TextRecord('abc').to_bytes()
    b'\\xb6\\x06a\\x00b\\x00c\\x00'
    >>> UnicodeChars32TextRecord('abc').to_bytes()
    b'\\xba\\x06\\x00\\x00\\x00a\\x00b\\x00c\\x00'
    >>> from io import BytesIO
    >>> str(UnicodeChars32TextRecord.parse(BytesIO(b'\\x04\\x00\\x00\\x003\\x002\\x00')))
    '32'
    """

    def _encode(self):
        return self.value.encode('utf-16le')

    @classmethod
    def _decode(cls, data):
        if len(data) % 2:
            raise WcfBinaryError('UTF-16 byte length must be even')
        return data.decode('utf-16le')


class UnicodeChars8TextRecord(_Utf16Text):
    type = 0xB6


class UnicodeChars16TextRecord(_Utf16Text):
    type = 0xB8
    _length_format = '<H'


class UnicodeChars32TextRecord(_Utf16Text):
    """MC-NBFX 2.2.3.29 describes the Length as a MultiByteInt31, but the
    example of section 3 ("BA 04 00 00 00 33 00 32 00" for "32") and the
    .NET XmlBinaryReader (ReadUInt31(), a non-negative Int32) use a
    4-byte INT32, as for Chars32Text and Bytes32Text."""
    type = 0xBA
    _length_format = '<i'


class QNameDictionaryTextRecord(Text):
    type = 0xBC

    def __init__(self, prefix, index):
        self.prefix = prefix
        self.index = index

    def to_bytes(self):
        """
        >>> QNameDictionaryTextRecord('b', 2).to_bytes()
        b'\\xbc\\x01\\x02'
        """
        if len(self.prefix) != 1 or not 'a' <= self.prefix <= 'z':
            raise WcfBinaryError('QNameDictionaryText prefix must be a-z')
        dictionary[self.index]  # never write an id unknown to the peer
        bt = struct.pack(b'<B', self.type)
        bt += struct.pack(b'<B', ord(self.prefix) - ord('a'))
        bt += mbi31_bytes(self.index)
        return bytes(bt)

    def __str__(self):
        """
        >>> str(QNameDictionaryTextRecord('b', 2))
        'b:Envelope'
        """
        return '%s:%s' % (self.prefix, dictionary[self.index])

    @classmethod
    def parse(cls, fp):
        """
        >>> from io import BytesIO
        >>> fp = BytesIO(b'\\x01\\x02')
        >>> str(QNameDictionaryTextRecord.parse(fp))
        'b:Envelope'
        """
        prefix_index = read_struct(fp, '<B')
        if prefix_index >= 26:
            raise WcfBinaryError('Invalid QNameDictionaryText prefix index')
        prefix = chr(prefix_index + ord('a'))
        index = read_mbi31(fp)
        dictionary[index]  # an id unknown when decoding is refused
        return cls(prefix, index)


class FloatTextRecord(_FixedSizeText):
    type = 0x90
    xml_safe = True
    max_chars = 15
    _format = '<f'
    _value_types = (int, float)

    def __str__(self):
        """
        >>> str(FloatTextRecord(float('-inf')))
        '-INF'
        >>> str(FloatTextRecord(-0.0))
        '-0'
        >>> str(FloatTextRecord(1.337))
        '1.337'
        >>> FloatTextRecord(1.337).to_bytes()
        b'\\x90\\xd1"\\xab?'
        """
        return _shortest_ieee754_text(self.value, single_precision=True)


class DoubleTextRecord(_FixedSizeText):
    type = 0x92
    xml_safe = True
    max_chars = 24
    _format = '<d'
    _value_types = (int, float)

    def __str__(self):
        """
        >>> str(DoubleTextRecord(1.337))
        '1.337'
        >>> DoubleTextRecord(1.337).to_bytes()
        b'\\x921\\x08\\xac\\x1cZd\\xf5?'
        """
        return _shortest_ieee754_text(self.value, single_precision=False)


class DecimalTextRecord(Text):
    type = 0x94
    max_chars = 31

    def __init__(self, value):
        if not isinstance(value, Decimal):
            raise TypeError('DecimalTextRecord value must be a wcf.datatypes.Decimal, '
                            'not %s' % type(value).__name__)
        self.value = value

    def __str__(self):
        r"""
        >>> str(DecimalTextRecord(Decimal(False, 0, 1337, 3)))
        '1.337'
        """
        return str(self.value)

    def to_bytes(self):
        r"""
        >>> DecimalTextRecord(Decimal(False, 0, 1337, 3)).to_bytes()
        b'\x94\x00\x00\x03\x00\x00\x00\x00\x009\x05\x00\x00\x00\x00\x00\x00'
        """
        return bytes(super(DecimalTextRecord, self).to_bytes() +
                     self.value.to_bytes())

    @classmethod
    def parse(cls, fp):
        r"""
        >>> from io import BytesIO
        >>> fp = BytesIO(b'\x00\x00\x03\x00\x00\x00\x00\x009\x05\x00\x00\x00\x00\x00\x00')
        >>> str(DecimalTextRecord.parse(fp))
        '1.337'
        """
        value = Decimal.parse(fp)
        return cls(value)


def _local_utc_offset(utc_ticks):
    """The UTC offset (in ticks) of the decoding host at a UTC time, or its
    current offset where the host cannot compute it.

    time.localtime() rather than datetime.astimezone(): 7 times cheaper
    (it is called for every local DateTimeText rendered, array items
    included) and it covers years 1 to 9999 where the platform's time_t
    does.
    """
    try:
        return time.localtime((utc_ticks - _UNIX_EPOCH_TICKS) //
                              TICKS_PER_SECOND).tm_gmtoff * TICKS_PER_SECOND
    except (OverflowError, OSError, ValueError):
        return time.localtime().tm_gmtoff * TICKS_PER_SECOND


class DatetimeTextRecord(Text):
    """``value``: the 62-bit field; ``tz``: 0 unspecified, 1 UTC, 2 local
    (MC-NBFX 2.2.3.12).

    For tz 0 and 1, ``value`` is the ticks (100 ns) since 0001-01-01 of the
    date. For a local time, it is what .NET's DateTime.ToBinary() writes
    and FromBinary() reads, .NET being the producer of these records: the
    ticks of the UTC time, a time before 0001-01-01T00:00:00Z being stored
    below TICKS_CEILING. It is rendered as the local time of the decoding
    host with its offset (2.2.3.12: "The UTC offset MUST be the time zone
    offset in which the document is being decoded"). Taking the field as
    the local time itself shifts the values of .NET by the offset
    (checked against .NET Framework 4.8.1).
    """
    type = 0x96
    xml_safe = True
    max_chars = 33

    def __init__(self, value, tz):
        for name, field in (('value', value), ('tz', tz)):
            if field.__class__ is not int:
                raise TypeError('DatetimeTextRecord %s must be int, not %s'
                                % (name, type(field).__name__))
        self.value = value
        self.tz = tz

    def _check(self):
        limit = TICKS_CEILING if self.tz == 2 else MAX_DATETIME_TICKS
        if self.tz not in (0, 1, 2) or not 0 <= self.value < limit:
            raise WcfBinaryError('Invalid MC-NBFX DateTimeText value %r or time zone %r'
                                 % (self.value, self.tz))

    def _local(self):
        """(ticks, UTC offset in ticks) of a local time, as
        DateTime.FromBinary() computes them."""
        ticks = self.value
        if ticks > TICKS_CEILING - TICKS_PER_DAY:
            ticks -= TICKS_CEILING  # before 0001-01-01T00:00:00Z
        offset = _local_utc_offset(min(max(ticks, 0), MAX_DATETIME_TICKS - 1))
        # whole minutes, truncated towards zero, as written: a local mean
        # time offset (+00:09:21) would otherwise shift the instant
        minute = 60 * TICKS_PER_SECOND
        offset = offset // minute * minute if offset >= 0 else -(-offset // minute * minute)
        ticks += offset
        if ticks < 0:
            ticks += TICKS_PER_DAY  # as .NET does
        if not 0 <= ticks < MAX_DATETIME_TICKS:
            raise WcfBinaryError('MC-NBFX DateTimeText local time out of range')
        return ticks, offset

    def __str__(self):
        """DateTimeText lexical format (MC-NBFX 2.2.3.12).

        The time is always written: the text of 2.2.3.12 drops it at
        midnight ("yyyy-MM-dd"), but the example of MC-NBFX section 3
        ("2006-05-17T00:00:00") and .NET (XmlConverter.ToChars(DateTime))
        do not.
        """
        self._check()
        ticks, offset = self._local() if self.tz == 2 else (self.value, 0)
        days, rem = divmod(ticks, TICKS_PER_DAY)
        seconds, fraction = divmod(rem, TICKS_PER_SECOND)
        date = datetime.date.fromordinal(days + 1)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        text = '%04d-%02d-%02dT%02d:%02d:%02d' % (
            date.year, date.month, date.day, hours, minutes, seconds)
        text += _fraction(fraction)
        if self.tz == 1:
            text += 'Z'
        elif self.tz == 2:
            minutes = offset // (60 * TICKS_PER_SECOND)  # exact: whole minutes
            text += '%s%02d:%02d' % ('+' if minutes >= 0 else '-',
                                    abs(minutes) // 60, abs(minutes) % 60)
        return text

    def to_bytes(self):
        """
        >>> str(''.join('%02X' % i for i in DatetimeTextRecord(632834208000000000, 0).to_bytes()))
        '9600408EF95B47C808'
        >>> str(''.join('%02X' % i for i in DatetimeTextRecord(632834208000000000, 2).to_bytes()))
        '9600408EF95B47C888'
        """
        self._check()
        return bytes((self.type,)) + struct.pack('<Q', (self.tz << 62) | self.value)

    @classmethod
    def parse(cls, fp):
        """
        >>> from io import BytesIO
        >>> fp = BytesIO(b'\\xFF\\x3F\\x37\\xF4\\x75\\x28\\xCA\\x2B')
        >>> str(DatetimeTextRecord.parse(fp))
        '9999-12-31T23:59:59.9999999'
        >>> fp = BytesIO(b'\\x00\\x40\\x8E\\xF9\\x5B\\x47\\xC8\\x08')
        >>> str(DatetimeTextRecord.parse(fp))
        '2006-05-17T00:00:00'
        """
        data = read_struct(fp, '<Q')
        record = cls(data & 0x3FFFFFFFFFFFFFFF, data >> 62)
        record._check()
        return record


class Chars8TextRecord(_Utf8Text):
    type = 0x98


class Chars16TextRecord(_Utf8Text):
    type = 0x9A
    _length_format = '<H'


class Chars32TextRecord(_Utf8Text):
    type = 0x9C
    _length_format = '<i'
    _positive = True


class UniqueIdTextRecord(Text):
    type = 0xAC
    xml_safe = True
    max_chars = 45

    def __init__(self, *args, **kwargs):
        self.uuid = uuid.UUID(*args, **kwargs)

    def to_bytes(self):
        """
        >>> UniqueIdTextRecord('urn:uuid:33221100-5544-7766-8899-aabbccddeeff').to_bytes()
        b'\\xac\\x00\\x11"3DUfw\\x88\\x99\\xaa\\xbb\\xcc\\xdd\\xee\\xff'
        """
        bt = super(UniqueIdTextRecord, self).to_bytes()
        bt += self.uuid.bytes_le

        return bytes(bt)

    def __str__(self):
        r"""
        >>> str(UniqueIdTextRecord('urn:uuid:33221100-5544-7766-8899-aabbccddeeff'))
        'urn:uuid:33221100-5544-7766-8899-aabbccddeeff'
        """
        return self.uuid.urn

    @classmethod
    def parse(cls, fp):
        r"""
        >>> from io import BytesIO
        >>> fp = BytesIO(b'\x00\x11"3DUfw\x88\x99\xaa\xbb\xcc\xdd\xee\xff')
        >>> str(UniqueIdTextRecord.parse(fp))
        'urn:uuid:33221100-5544-7766-8899-aabbccddeeff'
        """
        u = read_exact(fp, 16)

        return cls(bytes_le=u)


class UuidTextRecord(UniqueIdTextRecord):
    type = 0xB0
    xml_safe = True
    max_chars = 36

    def __str__(self):
        """
        >>> str(UuidTextRecord('urn:uuid:33221100-5544-7766-8899-aabbccddeeff'))
        '33221100-5544-7766-8899-aabbccddeeff'
        """
        return str(self.uuid)


class _BytesText(_LengthPrefixedText):
    """Binary data, rendered as base64 (MC-NBFX 2.2.3.16 to 2.2.3.18).

    >>> Bytes8TextRecord(b'abc').to_bytes()
    b'\\x9e\\x03abc'
    >>> Bytes32TextRecord(b'abc').to_bytes()
    b'\\xa2\\x03\\x00\\x00\\x00abc'
    >>> str(Bytes16TextRecord(b'abc'))
    'YWJj'
    """

    def __init__(self, value):
        if not isinstance(value, (bytes, bytearray, memoryview)):
            raise TypeError('%s value must be bytes, not %s'
                            % (type(self).__name__, type(value).__name__))
        super().__init__(value)

    def __str__(self):
        return base64.b64encode(self.value).decode()

    def char_count(self):
        return 4 * ((len(self.value) + 2) // 3)  # base64, without encoding it

    def _encode(self):
        return bytes(self.value)

    @classmethod
    def _decode(cls, data):
        return data


class Bytes8TextRecord(_BytesText):
    type = 0x9E
    xml_safe = True


class Bytes16TextRecord(_BytesText):
    type = 0xA0
    xml_safe = True
    _length_format = '<H'


class Bytes32TextRecord(_BytesText):
    type = 0xA2
    xml_safe = True
    _length_format = '<i'
    _positive = True


class StartListTextRecord(Text):
    type = 0xA4
    with_end_element = False  # 0xA5 is reserved

    def __init__(self, values=None):
        self.values = list(values) if values is not None else []

    def __str__(self):
        return ' '.join(str(value) for value in self.values)

    def char_count(self):
        return 0  # the items are charged as they are read

    def to_bytes(self):
        result = bytearray((self.type,))
        for value in self.values:
            if (not isinstance(value, Text) or not value.standalone or
                    isinstance(value, StartListTextRecord)):
                raise WcfBinaryError('WCF text list must contain non-list text records')
            result.extend(value.to_bytes())
        result.append(EndListTextRecord.type)
        return bytes(result)

    @classmethod
    def parse(cls, fp):
        values = []
        while True:
            item = fp.read(1)
            if not item:
                raise WcfBinaryError('Unterminated StartListText')
            code = item[0]
            if code == EndListTextRecord.type:
                break
            item_cls = Record.records.get(code)
            if (item_cls is None or not issubclass(item_cls, Text) or
                    not item_cls.standalone or issubclass(item_cls, cls)):
                raise WcfBinaryError('Invalid record 0x%02X inside a WCF text list' % code)
            item = item_cls.parse(fp)
            charge(1, item.char_count() + 1)  # and its separator
            values.append(item)
        return cls(values)


class EndListTextRecord(Text):
    """Only valid closing a StartListText."""
    type = 0xA6
    max_chars = 0
    standalone = False
    with_end_element = False  # 0xA7 is reserved


class EmptyTextRecord(Text):
    type = 0xA8
    xml_safe = True
    max_chars = 0

    def __str__(self):
        return ''


class TimeSpanTextRecord(_FixedSizeText):
    type = 0xAE
    xml_safe = True
    max_chars = 27
    _format = '<q'

    def __str__(self):
        """The xsd:duration form, as .NET XmlConvert.ToString(TimeSpan).

        MC-NBFX 2.2.3.23 describes a "[DDDDDDDD.]HH:mm:ss[.fffffff]"
        form, but the examples of MC-NBFX section 3 ("-PT5M44S",
        "PT3H20M") and .NET, whose reader returns
        XmlConvert.ToString(TimeSpan), use xsd:duration, which is also
        what DataContract deserializes a TimeSpan from.

        >>> str(TimeSpanTextRecord(-3440000000))
        '-PT5M44S'
        >>> str(TimeSpanTextRecord(120000000000))
        'PT3H20M'
        >>> str(TimeSpanTextRecord(0))
        'PT0S'
        >>> TimeSpanTextRecord(36000000).to_bytes()
        b'\\xae\\x00Q%\\x02\\x00\\x00\\x00\\x00'
        """
        ticks = abs(self.value)
        seconds, fraction = divmod(ticks, TICKS_PER_SECOND)
        days, seconds = divmod(seconds, 86400)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        text = '-P' if self.value < 0 else 'P'
        if days:
            text += '%dD' % days
        if hours or minutes or seconds or fraction:
            text += 'T'
            if hours:
                text += '%dH' % hours
            if minutes:
                text += '%dM' % minutes
            if seconds or fraction:
                text += '%d%sS' % (seconds, _fraction(fraction))
        if text.endswith('P'):
            text += 'T0S'
        return text


class DictionaryTextRecord(Text):
    type = 0xAA

    def __init__(self, index):
        self.index = index

    def to_bytes(self):
        r"""
        >>> DictionaryTextRecord(2).to_bytes()
        b'\xaa\x02'
        """
        dictionary[self.index]  # never write an id unknown to the peer
        return bytes(super(DictionaryTextRecord, self).to_bytes() +
                     mbi31_bytes(self.index))

    def __str__(self):
        r"""
        >>> str(DictionaryTextRecord(2))
        'Envelope'
        """
        return dictionary[self.index]

    @classmethod
    def parse(cls, fp):
        r"""
        >>> from io import BytesIO
        >>> fp = BytesIO(b'\x02')
        >>> str(DictionaryTextRecord.parse(fp))
        'Envelope'
        """
        index = read_mbi31(fp)
        dictionary[index]  # an id unknown when decoding is refused
        return cls(index)


Record.add_records((ZeroTextRecord,
                    OneTextRecord,
                    FalseTextRecord,
                    TrueTextRecord,
                    Int8TextRecord,
                    Int16TextRecord,
                    Int32TextRecord,
                    Int64TextRecord,
                    UInt64TextRecord,
                    BoolTextRecord,
                    UnicodeChars8TextRecord,
                    UnicodeChars16TextRecord,
                    UnicodeChars32TextRecord,
                    QNameDictionaryTextRecord,
                    FloatTextRecord,
                    DoubleTextRecord,
                    DecimalTextRecord,
                    DatetimeTextRecord,
                    Chars8TextRecord,
                    Chars16TextRecord,
                    Chars32TextRecord,
                    UniqueIdTextRecord,
                    UuidTextRecord,
                    Bytes8TextRecord,
                    Bytes16TextRecord,
                    Bytes32TextRecord,
                    StartListTextRecord,
                    EndListTextRecord,
                    EmptyTextRecord,
                    TimeSpanTextRecord,
                    DictionaryTextRecord,))
