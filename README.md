python-wcfbin
=============

A python library for converting between WCF binary xml and plain xml.

A more complete documentation could be found in the doc directory (build with sphinx).
The changes of each version are in `CHANGES.md`.


Contributors
------------

- dannyquist
- sschmieda
- philiptzou


## Revised XML conversion behavior

**Values are lexical text by default.** MC-NBFX defines text records and typed
records, but XML without an XSD does not identify value types. This version
encodes element content and attribute values as UTF-8 `Chars8/16/32Text` by
default. It does **not** guess numbers, booleans, UUIDs, base64, or QNames.
For example, `<ClientVersion>8.0</ClientVersion>` stays `"8.0"` as text.
This is a deliberate behavior change to avoid corrupting version strings.

An **optional explicit type map** can request WCF record types for specific
fields. Paths use XML Clark-notation names (`{namespace-uri}localname`), and
attribute names start with `@`.

Example `types.json`:

```json
{
  "/{urn:demo}Envelope/{urn:demo}Request/{urn:demo}Amount": "double",
  "/{urn:demo}Envelope/{urn:demo}Request/@requestId": "uuid"
}
```

Run:

```sh
python xml2wcf.py input.xml --types types.json > request.bin
python wcf2xml.py request.bin > output.xml
```

Python API:

```python
from io import BytesIO
from wcf.xml2records import XMLParser
from wcf.records import Record, dump_records, render_xml

records = XMLParser.parse('<Version>8.0</Version>')
wire = dump_records(records)
print(render_xml(Record.parse(BytesIO(wire))))

# Preserve decoded wire types by editing the Record tree directly.
parsed = Record.parse(BytesIO(wire))
parsed[0].childs[0].value = '9.0'
new_wire = dump_records(parsed)
```

Explicit types currently supported: `text`/`string`, `int8`, `int16`, `int32`,
`int64`, `uint64`, `bool`, `float`, `double`, `decimal`, `uuid`, `uniqueid`,
`bytes`/`base64`. Wrong types or out-of-range values raise `WcfBinaryError`
instead of silently downgrading to text.

### Fidelity and scope

* `Record.parse(...)` retains binary record classes and whether an element was
  terminated by `EndElement` or a `*WithEndElement` marker. `dump_records(...)`
  does not mutate records. This supports lossless binary record round-trips for
  implemented record types; changing data may of course change the bytes.
* `render_xml(...)` is an XML **textual** representation, not a persistent
  typed intermediate representation. Exporting only the XML and converting it
  back to binary cannot reconstruct original WCF record types. Keep the record
  tree in memory for typed editing, or store your own type map separately.
* This is an **MC-NBFX / MC-NBFS / MC-NBFSE document codec**, not a full WCF
  client/server, SOAP transport, or MC-NMF framing/negotiation implementation.
  Sessionful applications must keep an independent BinaryXmlSession for each
  direction and connection. Interoperability with a particular Microsoft
  service still requires testing against its actual contract and endpoint.
* XML DTD and processing instructions are rejected rather than silently lost.
  Byte-exact preservation of original XML syntax (quoting style, entity form,
  self-closing syntax) is not supported, only equivalent XML character data.


### Untrusted input: errors and quotas

Every invalid, unsupported or over-quota input raises
`wcf.errors.WcfBinaryError` (a `ValueError`): truncated records, reserved
record types, unknown dictionary ids (`UnknownDictionaryId`, also a
`KeyError`), malformed XML, invalid UTF-8... `TypeError` is kept for wrong
uses of the API.

As MC-NBFX and MC-NBFSE (section 4) ask, decoding is bounded: a two-byte
DictionaryText can stand for a long dictionary string, an Array record for
millions of elements, and every record becomes a Python object.
`Record.parse(fp, quotas)` refuses a document beyond its `Quotas` (in the
spirit of .NET's `XmlDictionaryReaderQuotas`): `max_depth` (64),
`max_records` (200,000, attributes, list and array items counted) and
`max_chars` (16 Mi characters represented, dictionary strings expanded and
array items repeated). `DEFAULT_QUOTAS` applies unless others are given;
`NO_QUOTAS` is for trusted input only (`wcf2xml.py --no-quotas`).
`BinaryXmlSession` also bounds each StringTable, the number of session
strings and their total size, and parses its documents with its `quotas`.

`render_xml()` never writes markup that the records do not contain: names
and prefixes must be XML NCNames, comments must be valid XML comments, and
characters are escaped as MC-NBFX 2.2.3.13.1 interprets them (characters
illegal in XML as `&#digits;`), line ends as character references so that
an XML parser keeps them.

### Where the text of the specification is not followed

When the text of a section contradicts both the examples of MC-NBFX
section 3 and the .NET implementation, the examples and .NET are followed:

* UnicodeChars32Text (2.2.3.29): the length is a 4-byte INT32, not a
  MultiByteInt31 (example "BA 04 00 00 00 33 00 32 00", .NET ReadUInt31()).
* TimeSpanText (2.2.3.23): rendered as an xsd:duration (`-PT5M44S`), as
  .NET's XmlConvert.ToString(TimeSpan), not as `[d.]HH:mm:ss`.
* DateTimeText (2.2.3.12): the time is always written
  (`2006-05-17T00:00:00`), also at midnight.
* DateTimeText with TZ=2 (local): the field holds the UTC ticks, as .NET's
  DateTime.ToBinary() writes them (the text does not say which ticks a
  local time stores); it is rendered as the local time of the decoding
  host with its offset, as DateTime.FromBinary() does.

Known differences with .NET where the text is followed:

* FloatText/DoubleText: exponential notation outside of the significant
  digits, e.g. 100 is `1E+2` (.NET writes `100`).
* MultiByteInt31: a non-minimal encoding is refused (.NET accepts it).
* DecimalText: trailing zeros are not written (`1.5` for 1.50).

### Sessionful MC-NBFSE (in-band StringTable)

MC-NBFSE prepends a StringTable to **each document**, assigning new strings
consecutive **odd** IDs 1, 3, 5, ... which can be referenced by subsequent
documents in the same session. The MC-NBFS built-in dictionary has even IDs.
The application, not this document codec, handles message framing and session
lifetime; never share an instance between different peers or directions.

```python
from wcf.session import BinaryXmlSession

sender = BinaryXmlSession()
receiver = BinaryXmlSession()

first = sender.encode_xml('<request>8.0</request>',
                          new_strings=['request', '8.0'])
assert receiver.parse_document(first).render_xml() == '<request>8.0</request>'

# Existing session strings are reused; the new StringTable is empty.
second = sender.encode_xml('<request>9.0</request>')
assert receiver.parse_document(second).render_xml() == '<request>9.0</request>'

# Keep the returned SessionDocument object if you need exact record types.
# Use .to_bytes() for binary round-trip and .render_xml() for readable XML.
```

All values remain *lexical strings* unless an explicit `type_overrides` map
requests a typed WCF record. DictionaryText is also a text representation,
not a float/int inference. If a lexical value occurs in the active static
or session dictionary, it can be emitted as a DictionaryText record.

One-document CLI commands (new session for each invocation):

```sh
python xml2wcf.py --nbfse --new-strings strings.json input.xml > session.bin
python wcf2xml.py --nbfse session.bin > session.xml
```

For **several** consecutive documents, use the Python `BinaryXmlSession` API
instead of invoking the CLI separately: each CLI invocation starts a fresh
session. Files and TCP WCF framing (MC-NMF), handshake, authentication, WSDL,
SOAP routing and transport are out of scope.

### Verification

```sh
python -m unittest discover -s tests -t .     # or: python -m tests.alltests
```

The suite includes the doctests of every module, the Microsoft published
wire examples, deterministic XML/session round-trips, malformed, truncated
and mutated binary inputs, the quotas, and IEEE-754 bit-pattern checks.
Passing local tests is not a statement of universal Microsoft WCF/.NET wire
interoperability.
