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


"""MC-NBFX primitive types: MultiByteInt31, String, DECIMAL, and the
reading of fixed-size fields."""

import re
import struct

from wcf.errors import WcfBinaryError

__all__ = ['MultiByteInt31', 'Utf8String', 'Decimal', 'read_exact',
           'read_struct']


def read_exact(fp, length):
    """Read exactly ``length`` bytes, WcfBinaryError on truncated input.

    >>> from io import BytesIO
    >>> read_exact(BytesIO(b'abc'), 2)
    b'ab'
    >>> read_exact(BytesIO(b'a'), 2)
    Traceback (most recent call last):
    ...
    wcf.errors.WcfBinaryError: Truncated WCF binary data (expected 2 bytes, got 1)
    """
    data = fp.read(length)
    if len(data) != length:
        raise WcfBinaryError('Truncated WCF binary data (expected %d bytes, got %d)'
                         % (length, len(data)))
    return data


def read_struct(fp, fmt):
    """Read and unpack one fixed-size little-endian value.

    >>> from io import BytesIO
    >>> read_struct(BytesIO(b'\\xff\\xff'), '<h')
    -1
    """
    return struct.unpack(fmt, read_exact(fp, struct.calcsize(fmt)))[0]


class MultiByteInt31(object):

    def __init__(self, *args):
        self.value = args[0] if len(args) else None

    def to_bytes(self):
        """
        >>> MultiByteInt31(268435456).to_bytes()
        b'\\x80\\x80\\x80\\x80\\x01'
        >>> MultiByteInt31(0x7f).to_bytes()
        b'\\x7f'
        >>> MultiByteInt31(0x3fff).to_bytes()
        b'\\xff\\x7f'
        >>> MultiByteInt31(0x1fffff).to_bytes()
        b'\\xff\\xff\\x7f'
        >>> MultiByteInt31(0xfffffff).to_bytes()
        b'\\xff\\xff\\xff\\x7f'
        >>> MultiByteInt31(0x3fffffff).to_bytes()
        b'\\xff\\xff\\xff\\xff\\x03'
        """
        value = self.value
        if not isinstance(value, int) or not 0 <= value <= 0x7fffffff:
            raise WcfBinaryError('MultiByteInt31 must be an unsigned 31-bit integer')
        out = bytearray()
        while value > 0x7F:
            out.append(value & 0x7F | 0x80)
            value >>= 7
        out.append(value)
        return bytes(out)

    def __str__(self):
        return str(self.value)

    @classmethod
    def parse(cls, fp):
        """
        >>> from io import BytesIO
        >>> fp = BytesIO(b'\\x7f')
        >>> mb = MultiByteInt31.parse(fp)
        >>> mb.value
        127
        >>> fp = BytesIO(b'\\xff\\x7f')
        >>> mb = MultiByteInt31.parse(fp)
        >>> mb.value
        16383
        >>> fp = BytesIO(b'\\xb9\\x0a')
        >>> mb = MultiByteInt31.parse(fp)
        >>> mb.value
        1337
        """
        value = 0
        for pos in range(5):
            octet = fp.read(1)
            if len(octet) != 1:
                raise WcfBinaryError('Truncated MultiByteInt31')
            byte = octet[0]
            if pos == 4:
                if byte & 0xF8:
                    raise WcfBinaryError('Invalid fifth byte in MultiByteInt31')
                value |= byte << 28
                if value < (1 << 28):
                    raise WcfBinaryError('Non-canonical MultiByteInt31 length')
                return cls(value)
            value |= (byte & 0x7F) << (pos * 7)
            if not byte & 0x80:
                if pos and value < (1 << (7 * pos)):
                    raise WcfBinaryError('Non-canonical MultiByteInt31 length')
                return cls(value)



class Utf8String(object):

    def __init__(self, *args):
        self.value = args[0] if len(args) else None
        if isinstance(self.value, bytes):
            self.value = str(self.value, 'utf-8')

    def to_bytes(self):
        """
        >>> Utf8String("abc").to_bytes()
        b'\\x03\x61\x62\x63'
        >>> Utf8String("\xfcber").to_bytes()
        b'\\x05\\xc3\\xbcber'
        >>> Utf8String(b"\\xc3\\xbcber".decode('utf-8')).to_bytes()
        b'\\x05\\xc3\\xbcber'
        """
        data = self.value.encode('utf-8')
        strlen = len(data)

        return bytes(MultiByteInt31(strlen).to_bytes() + data)

    def __str__(self):
        return str(self.value)

    @classmethod
    def parse(cls, fp):
        """
        >>> from io import BytesIO
        >>> fp = BytesIO(b"\\x05\\xc3\\xbcber")
        >>> s = Utf8String.parse(fp)
        >>> s.to_bytes()
        b'\\x05\\xc3\\xbcber'
        >>> print(str(s))
        über
        """
        length = MultiByteInt31.parse(fp).value
        return cls(read_exact(fp, length).decode('utf-8'))


class Decimal(object):
    """A [MS-OAUT] 2.2.26 DECIMAL: a 96-bit coefficient (high 32 bits,
    low 64 bits), a sign and a scale (0 to 28 decimal places)."""

    # the xsd:decimal lexical space: no exponent
    _LEXICAL = re.compile(r'([+-]?)([0-9]*)(?:\.([0-9]*))?')

    def __init__(self, sign, high, low, scale):
        if not 0 <= scale <= 28:
            raise WcfBinaryError('scale %d isn\'t between 0 and 28' % scale)
        if not (0 <= high < 1 << 32 and 0 <= low < 1 << 64):
            raise WcfBinaryError('Decimal coefficient out of the 96-bit range')
        self.sign = sign
        self.high = high
        self.low = low
        self.scale = scale

    @classmethod
    def from_string(cls, text):
        """Parse an xsd:decimal (WcfBinaryError when it is not one or does not
        fit in a DECIMAL).

        >>> str(Decimal.from_string('-12.50'))
        '-12.5'
        >>> Decimal.from_string('1E+999999999')
        Traceback (most recent call last):
        ...
        wcf.errors.WcfBinaryError: Invalid decimal '1E+999999999'
        """
        match = cls._LEXICAL.fullmatch(text.strip())
        if match is None or not (match.group(2) or match.group(3)):
            raise WcfBinaryError('Invalid decimal %r' % (text,))
        sign, integer, fraction = match.group(1), match.group(2), match.group(3) or ''
        if len(fraction) > 28:
            fraction = fraction.rstrip('0')
        digits = (integer + fraction).lstrip('0')
        # 2^96 has 29 digits: checked before any conversion
        if len(fraction) > 28 or len(digits) > 29:
            raise WcfBinaryError('Decimal %r out of the DECIMAL range' % (text,))
        coefficient = int(digits or '0')
        if coefficient >= 1 << 96:
            raise WcfBinaryError('Decimal %r out of the DECIMAL range' % (text,))
        return cls(sign == '-', coefficient >> 64, coefficient & ((1 << 64) - 1),
                   len(fraction))

    def to_bytes(self):
        """
        >>> Decimal(False, 0, 5123456, 6).to_bytes()
        b'\\x00\\x00\\x06\\x00\\x00\\x00\\x00\\x00\\x80-N\\x00\\x00\\x00\\x00\\x00'
        """
        return struct.pack('<HBBIQ', 0, self.scale, 0x80 if self.sign else 0,
                           self.high, self.low)

    def __str__(self):
        """
        >>> str(Decimal(False, 0, 1234, 3))
        '1.234'
        >>> str(Decimal(False, 0, 1234, 1))
        '123.4'
        >>> str(Decimal(True, 0, 1234, 1))
        '-123.4'
        >>> str(Decimal(False, 0, 5123456, 6))
        '5.123456'

        A negative zero is written "0", as .NET does (the text of MC-NBFX
        2.2.3.11 does not cover it):

        >>> str(Decimal(True, 0, 0, 2))
        '0'
        """
        if not self.high and not self.low:
            return '0'
        value = str(self.high * 2**64 + self.low)
        if self.scale > 0:
            value = value.zfill(self.scale + 1)
            value = (value[:-self.scale] + '.' + value[-self.scale:]).rstrip('0').rstrip('.')
        if self.sign:
            value = '-%s' % value
        return value

    @classmethod
    def parse(cls, fp):
        """
        >>> from io import BytesIO
        >>> buf = BytesIO(b'\\x00\\x00\\x06\\x00\\x00\\x00\\x00\\x00\\x80-N\\x00\\x00\\x00\\x00\\x00')
        >>> str(Decimal.parse(buf))
        '5.123456'
        """
        # wReserved "MUST be set to 0 and MUST be ignored by the
        # recipient" ([MS-OAUT] 2.2.26)
        _, scale, sign, high, low = struct.unpack('<HBBIQ', read_exact(fp, 16))
        if sign not in (0, 0x80):
            raise WcfBinaryError('Invalid Decimal sign bits')
        return cls(bool(sign), high, low, scale)


if __name__ == '__main__':
    import doctest
    doctest.testmod()
