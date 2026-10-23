"""MC-NBFSE session dictionaries for WCF Binary XML.

MC-NBFSE is a *document codec* extension, not the MC-NMF transport framing.
Each document is prefixed by a StringTable: a MultiByteInt31 byte length and
zero or more length-prefixed UTF-8 strings. Session IDs start at 1 and advance
by two; already introduced entries are referenced in later documents.

Use a separate :class:`BinaryXmlSession` for each connection/direction. Both
sides of a duplex exchange maintain their own dictionaries and lifetimes.
"""

from contextlib import contextmanager
from io import BytesIO

from wcf.datatypes import MultiByteInt31, Utf8String
from wcf.dictionary import dictionary_context, static_inverted_dict
from wcf.records import Record, dump_records, render_xml
from wcf.xml2records import XMLParser


class SessionDocument:
    """An NBFX tree with the StringTable and resolver that produced it.

    Use :meth:`to_bytes` for a byte-preserving round trip if records have not
    been modified.  Use :meth:`render_xml` or :meth:`context` to resolve odd
    dictionary IDs even after the decoding session processes more messages.
    """

    def __init__(self, records, new_strings, dictionary_snapshot):
        self.records = records
        self.new_strings = tuple(new_strings)
        self.dictionary = dict(dictionary_snapshot)

    @contextmanager
    def context(self):
        with dictionary_context(self.dictionary):
            yield

    def render_xml(self):
        with self.context():
            return render_xml(self.records)

    def to_bytes(self):
        with self.context():
            return encode_string_table(self.new_strings) + dump_records(self.records)


def encode_string_table(strings):
    """Serialize a StringTable; Size counts *encoded* Strings, not characters.

    >>> encode_string_table(['é', 'long'])
    b'\x08\x02\xc3\xa9\x04long'
    >>> encode_string_table([])
    b'\x00'
    """
    data = b''.join(Utf8String(string).to_bytes() for string in strings)
    return MultiByteInt31(len(data)).to_bytes() + data


class BinaryXmlSession:
    """Parse and produce successive MC-NBFSE documents in one direction.

    Use ``parse_document`` to decode a full MC-NBFSE document (including the
    StringTable). Use ``encode_xml`` with ``new_strings`` to add new dictionary
    entries and start reusing them in the document and subsequent documents.

    Note: MC-NMF framing and negotiation (encoding 0x08) are separate.
    """

    def __init__(self, max_table_bytes=1024 * 1024, max_strings=65536,
                 max_document_bytes=16 * 1024 * 1024):
        self._entries = {}
        self._value_to_id = {}
        self._max_table_bytes = max_table_bytes
        self._max_strings = max_strings
        self._max_document_bytes = max_document_bytes

    @property
    def dictionary(self):
        """Copy of all session entries, with odd integer IDs."""
        return self._entries.copy()

    def reset(self):
        """Reset at the end of an MC-NMF session; never retain across peers."""
        self._entries.clear()
        self._value_to_id.clear()

    @contextmanager
    def context(self):
        """Activate dictionary resolution for inspecting/manipulating trees."""
        with dictionary_context(self._entries):
            yield

    def _accept_strings(self, strings):
        if len(self._entries) + len(strings) > self._max_strings:
            raise ValueError('MC-NBFSE session dictionary limit exceeded')
        known = set(self._value_to_id)
        for string in strings:
            if not isinstance(string, str):
                raise TypeError('MC-NBFSE strings must be Unicode')
            if string in known:
                raise ValueError('Duplicate MC-NBFSE session string: %r' % string)
            known.add(string)
        updated = self._entries.copy()
        next_id = 2 * len(updated) + 1
        for string in strings:
            updated[next_id] = string
            next_id += 2
        return updated

    def parse_document(self, data):
        if len(data) > self._max_document_bytes:
            raise ValueError('MC-NBFSE document size limit exceeded')
        fp = BytesIO(data)
        size = MultiByteInt31.parse(fp).value
        if size > self._max_table_bytes:
            raise ValueError('MC-NBFSE StringTable size limit exceeded')
        table = fp.read(size)
        if len(table) != size:
            raise ValueError('Truncated MC-NBFSE StringTable')
        table_fp = BytesIO(table)
        new_strings = []
        while table_fp.tell() < size:
            new_strings.append(Utf8String.parse(table_fp).value)
            if len(self._entries) + len(new_strings) > self._max_strings:
                raise ValueError('MC-NBFSE session dictionary limit exceeded')
        if table_fp.tell() != size:
            raise ValueError('MC-NBFSE StringTable does not match declared size')
        updated = self._accept_strings(new_strings)
        with dictionary_context(updated):
            records = Record.parse(fp)
            # Force dictionary lookups on all attributes/text to catch unknown
            # IDs, instead of deferring errors until after session commit.
            render_xml(records)
        # Commit only after validating the *entire* document.
        self._entries = updated
        self._value_to_id = {value: key for key, value in updated.items()}
        return SessionDocument(records, new_strings, updated)

    def encode_records(self, records, new_strings=()):
        """Encode typed records, preserving their NBFX record types."""
        new_strings = tuple(new_strings)
        updated = self._accept_strings(new_strings)
        header = encode_string_table(new_strings)
        table_size = sum(len(Utf8String(item).to_bytes()) for item in new_strings)
        if table_size > self._max_table_bytes:
            raise ValueError('MC-NBFSE StringTable size limit exceeded')
        with dictionary_context(updated):
            # Ensure no unresolved odd IDs are serialized by accident.
            render_xml(records)
            data = header + dump_records(records)
        if len(data) > self._max_document_bytes:
            raise ValueError('MC-NBFSE document size limit exceeded')
        self._entries = updated
        self._value_to_id = {value: key for key, value in updated.items()}
        return data

    def encode_xml(self, xml, new_strings=(), type_overrides=None):
        """Encode XML using text by default and optional explicit types.

        ``new_strings`` may include element/attribute local names, namespace
        URIs or values. Previously registered strings are reused automatically.
        """
        new_strings = tuple(new_strings)
        updated = self._accept_strings(new_strings)
        with dictionary_context(updated):
            records = XMLParser.parse(xml, type_overrides=type_overrides,
                                      dictionary_text=True)
        return self.encode_records(records, new_strings=new_strings)
