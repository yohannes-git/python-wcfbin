"""MC-NBFSE session dictionaries for WCF Binary XML.

MC-NBFSE is a *document codec* extension, not the MC-NMF transport framing.
Each document is prefixed by a StringTable: a MultiByteInt31 byte length and
zero or more length-prefixed UTF-8 strings. Session IDs start at 1 and advance
by two; already introduced entries are referenced in later documents.

Use a separate :class:`BinaryXmlSession` for each connection/direction. Both
sides of a duplex exchange maintain their own dictionaries and lifetimes.
"""

from collections import ChainMap
from contextlib import contextmanager
from io import BytesIO

from wcf.errors import WcfBinaryError, binary_errors
from wcf.datatypes import MultiByteInt31, Utf8String, read_exact
from wcf.dictionary import dictionary_context
from wcf.records import DEFAULT_QUOTAS, Record, dump_records, render_xml
from wcf.xml2records import XMLParser


class SessionDocument:
    """An NBFX tree with the StringTable and resolver that produced it.

    Use :meth:`to_bytes` for a byte-preserving round trip if records have not
    been modified.  Use :meth:`render_xml` or :meth:`context` to resolve odd
    dictionary IDs even after the decoding session processes more messages.
    """

    def __init__(self, records, new_strings, entries, reverse=None):
        self.records = records
        self.new_strings = tuple(new_strings)
        # The session dictionary only grows (and reset() replaces it), so
        # the session's own mapping resolves the IDs of this document for
        # as long as it lives: no copy per document.
        self._entries = entries
        self._reverse = reverse

    @property
    def dictionary(self):
        """Copy of the session entries known when the document was parsed
        (and possibly some added later, with higher IDs)."""
        return dict(self._entries)

    @contextmanager
    def context(self):
        with dictionary_context(self._entries, self._reverse):
            yield

    def render_xml(self):
        with self.context():
            return render_xml(self.records)

    def to_bytes(self):
        with self.context():
            return encode_string_table(self.new_strings) + dump_records(self.records)


def encode_string_table(strings):
    r"""Serialize a StringTable; Size counts *encoded* Strings, not characters.

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

    MC-NBFSE section 4 asks consumers to limit the StringTables they accept:
    ``max_table_bytes`` bounds one StringTable, ``max_strings`` and
    ``max_session_bytes`` the whole session dictionary. ``quotas`` are the
    decoding quotas of each document (see wcf.records.Quotas).

    Note: MC-NMF framing and negotiation (encoding 0x08) are separate.
    """

    def __init__(self, max_table_bytes=1024 * 1024, max_strings=65536,
                 max_document_bytes=16 * 1024 * 1024,
                 max_session_bytes=4 * 1024 * 1024, quotas=DEFAULT_QUOTAS):
        self._max_table_bytes = max_table_bytes
        self._max_strings = max_strings
        self._max_document_bytes = max_document_bytes
        self._max_session_bytes = max_session_bytes
        self.quotas = quotas
        self.reset()

    @property
    def dictionary(self):
        """Copy of all session entries, with odd integer IDs."""
        return self._entries.copy()

    def reset(self):
        """Reset at the end of an MC-NMF session; never retain across peers.

        New mappings replace the old ones, which the documents already
        decoded keep using.
        """
        self._entries = {}
        self._value_to_id = {}
        self._session_bytes = 0

    @contextmanager
    def context(self):
        """Activate dictionary resolution for inspecting/manipulating trees."""
        with dictionary_context(self._entries, self._value_to_id):
            yield

    def _new_entries(self, strings, table_bytes):
        """The (id -> string, string -> id) mappings of new strings, checked
        against MC-NBFSE 2.1 and the session limits; nothing is committed."""
        if len(self._entries) + len(strings) > self._max_strings:
            raise WcfBinaryError('MC-NBFSE session dictionary limit exceeded')
        if self._session_bytes + table_bytes > self._max_session_bytes:
            raise WcfBinaryError('MC-NBFSE session dictionary size limit exceeded')
        entries, reverse = {}, {}
        next_id = 2 * len(self._entries) + 1
        for string in strings:
            # "Each String MUST be unique and MUST NOT have been present in
            # a prior StringTable."
            if string in self._value_to_id or string in reverse:
                raise WcfBinaryError('Duplicate MC-NBFSE session string: %.64r' % string)
            entries[next_id] = string
            reverse[string] = next_id
            next_id += 2
        return entries, reverse

    def _commit(self, entries, reverse, table_bytes):
        self._entries.update(entries)
        self._value_to_id.update(reverse)
        self._session_bytes += table_bytes

    def parse_document(self, data, quotas=None):
        """Decode one MC-NBFSE document: its StringTable, then the records,
        under ``quotas`` (the session's unless given).

        The strings of a valid StringTable join the session dictionary even
        if the document that follows is refused: the producer numbered
        them, and the IDs of the following documents count them (MC-NBFSE
        2.1, "A consumer of this format MUST maintain this mapping").
        """
        with binary_errors():
            return self._parse_document(data, quotas)

    def _parse_document(self, data, quotas):
        if len(data) > self._max_document_bytes:
            raise WcfBinaryError('MC-NBFSE document size limit exceeded')
        fp = BytesIO(data)
        size = MultiByteInt31.parse(fp).value
        if size > self._max_table_bytes:
            raise WcfBinaryError('MC-NBFSE StringTable size limit exceeded')
        table_fp = BytesIO(read_exact(fp, size))
        new_strings = []
        while table_fp.tell() < size:
            new_strings.append(Utf8String.parse(table_fp).value)
            if len(self._entries) + len(new_strings) > self._max_strings:
                raise WcfBinaryError('MC-NBFSE session dictionary limit exceeded')
        self._commit(*self._new_entries(new_strings, size), size)
        # Record.parse() resolves every dictionary reference
        with self.context():
            records = Record.parse(fp, self.quotas if quotas is None else quotas)
        return SessionDocument(records, new_strings, self._entries,
                               self._value_to_id)

    def encode_records(self, records, new_strings=()):
        """Encode typed records, preserving their NBFX record types."""
        return self._encode(new_strings, lambda: records)

    def encode_xml(self, xml, new_strings=(), type_overrides=None):
        """Encode XML using text by default and optional explicit types.

        ``new_strings`` may include element/attribute local names, namespace
        URIs or values. Previously registered strings are reused automatically.
        """
        return self._encode(new_strings, lambda: XMLParser.parse(
            xml, type_overrides=type_overrides, dictionary_text=True))

    def _encode(self, new_strings, make_records):
        """A document: the StringTable of ``new_strings``, then the records
        made by ``make_records()`` with those strings already in use. The
        strings join the session only if the document is produced."""
        new_strings = tuple(new_strings)
        if not all(isinstance(string, str) for string in new_strings):
            raise TypeError('MC-NBFSE strings must be Unicode')
        table = b''.join(Utf8String(string).to_bytes() for string in new_strings)
        if len(table) > self._max_table_bytes:
            raise WcfBinaryError('MC-NBFSE StringTable size limit exceeded')
        entries, reverse = self._new_entries(new_strings, len(table))
        # serializing resolves every dictionary reference: an ID unknown
        # to the peer cannot be written
        if entries:
            scope = dictionary_context(ChainMap(entries, self._entries),
                                       ChainMap(reverse, self._value_to_id))
        else:  # no ChainMap (Python lookups) without new strings
            scope = dictionary_context(self._entries, self._value_to_id)
        with scope:
            data = (MultiByteInt31(len(table)).to_bytes() + table +
                    dump_records(make_records()))
        if len(data) > self._max_document_bytes:
            raise WcfBinaryError('MC-NBFSE document size limit exceeded')
        self._commit(entries, reverse, len(table))
        return data
