# Microsoft MC-NBFX / MC-NBFS / MC-NBFSE follow-up review

Review date: 2026-10-23. Source: originally supplied `python-wcfbin-develop.zip`,
with the prior compliance corrections plus follow-up code in this archive.

## Executive status

**Targeted tests pass; full Microsoft WCF interoperability is not certified.**

- Static dictionary MC-NBFS: lookup and emission of even IDs, including the
  Microsoft SOAP example, plus original sample binary -> records -> identical
  bytes.
- MC-NBFX: recognized record types, reserved codes, explicit and implicit
  element endings, lists, arrays, UTF8/UTF16 strings, MultiByteInt31, numbers,
  DateTime/TimeSpan, decimal, namespaces and XML escaping have automated tests.
  Variable-length integers are now rejected when encoded using a packet width
  forbidden by the range mapping in MC-NBFX section 2.1.2.
- MC-NBFSE: per-document StringTables, odd ID allocation, ID reuse over several
  messages, state isolation, invalid table/unknown-ID rejection, rejection of
  repeated strings, session reset, preservation of record types. Uses a
  ContextVar-backed scoped dictionary to prevent cross-session contamination.
- XML -> NBFX: lexical string by default (including `8.0`); explicit field
  type mapping overrides this. In MC-NBFSE sessions, existing StringTable
  contents can be emitted as DictionaryText while remaining strings.
- Round-trip: binary -> record tree -> binary preserves tested wire encodings;
  binary -> plain XML -> binary does **not** in general preserve original
  record types, because plain XML carries no record type metadata.

## Verification run

Command: `python -m tests.alltests` in the project root, Python 3.13.
Result: **158 tests run, all 158 passed**.

Tests include 500 deterministic XML/session round-trips and 4000 fuzz-like
random short NBFX byte streams, as well as official Microsoft examples for
SOAP records and the MC-NBFSE two-string session table (`action`, `Inventory`).
The fuzz-like suite is not exhaustive or a security audit.

Additional CLI smoke tests: XML <-> NBFX; XML <-> NBFSE (one standalone document)
including a new StringTable; and the project's existing `example.bin`.

## Official references

- MC-NBFX protocol: https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfx/94c66ea1-e79a-4364-af88-1fa7fef2cc33
- MC-NBFX record list: https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfx/e17683ce-cb4c-4968-bd7a-ebfe5cc18a1e
- MC-NBFX Array: https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfx/e0cd55a8-016d-4bb7-924e-a8b7add5d52b
- MC-NBFS static dictionary: https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfs/9268bb11-94bf-451a-8827-955495e99c7b
- MC-NBFS SOAP example: https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfs/38195b75-e82a-4d17-a358-b79cec9d1f77
- MC-NBFSE StringTable: https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfse/a161304c-1a8a-4f31-beec-b96ebc9b1919
- MC-NBFSE SOAP examples: https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfse/0f335427-1b80-4b5d-a32e-e339e8acf376

## Outstanding limitations

1. **Live Microsoft .NET WCF/PowerShell interop not executed.** The current
   environment does not have `dotnet`, `mono`, `pwsh`, or credentials and a
   network address for a WCF service. This cannot be replaced by local tests.
   To validate a deployment, exchange requests and responses with the real
   service, checking version strings (`8.0`), SOAP namespace headers, typed
   attributes, arrays, dictionary reuse across successive messages, and both
   client/server directions.
2. **Not a WCF transport implementation.** MC-NMF handshake/framing, TCP/HTTP
   transports, authentication and WSDL-based service contracts are outside
   this project's scope. `BinaryXmlSession` operates on complete MC-NBFSE
   *documents*, not framed packets.
3. **Input resource quotas.** `BinaryXmlSession` enforces document/table count
   limits, but plain `Record.parse` is not a hardened network streaming parser
   with configurable recursion or per-record allocation quotas. Do not parse
   completely untrusted unbounded input without front-end size/resource limits.
4. **XML type and lexical fidelity.** An XML character view cannot preserve the
   original wire record classes. Named schemas may also require a particular
   record type even though MC-NBFX supports lexical text. Reuse decoded record
   trees or supply explicit overrides. XML declarations and self-closing syntax
   are not preserved byte-for-byte.
5. **Coverage.** The tests exercise important record types and Microsoft sample
   vectors, but are not a complete exhaustive proof of compliance with every
   subsection, corner case or interop service behavior.

## Independent re-audit and corrections (same date, v0.5.3.post2)

The prior review recorded **158 passed** before an independent audit identified
10 failing cases out of 14 new checks. All 10 have since been corrected.
The suite now has **185 tests passed**, including the 14 independent cases
and 13 additional boundary tests. An additional normative encoding defect
in `UnicodeChars32Text` was found and fixed. See
`CORRECTIONS_CONTRE_AUDIT.md` for full details. All limitations above,
including the absence of live .NET interop, still apply.
