# WCF Binary XML: targeted conformity fixes

This modified version starts from the user-provided
`python-wcfbin-develop.zip` (2023 snapshot). No changes were sent to GitHub.

## Corrected

| Area | Behavior in this revised archive | Reference |
| --- | --- | --- |
| XML -> WCF | Text records by default, including versions like `8.0`, integers, booleans, UUIDs and base64-looking strings. No automatic typing. | MC-NBFX 2.2.3, GitHub issue #15 |
| Explicit schema | Optional namespace-aware path mapping for chosen types on elements and attributes. Invalid lexical forms rejected. | MC-NBFX 2.2.3 |
| UTF-8 strings | MultiByteInt31 lengths decoded with all 1-5 bytes, 31-bit range validated. | MC-NBFX 2.1.2/2.1.3 |
| XML serializer | Reworked rendering to escape text/attributes correctly and preserve whitespace, mixed content and comments without pretty-printing insertions. | MC-NBFX 3 |
| Trees and closure | Serializer does not mutate record objects and preserves explicit/implicit end-element style on parsed trees. | MC-NBFX 2.1.1 |
| Arrays | Namespace declarations and attributes of ArrayRecord retained; prefixed closing tags correct; invalid empty arrays rejected. | MC-NBFX 2.3.3 |
| Numeric and time | Bool lowercase, NaN spelling, decimal leading/trailing zeros, TimeSpan ticks (100 ns), DateTime ticks (100 ns) and UTC/local date formats. | MC-NBFX 2.2.3.11 / .12 / .23 |
| List and empty text | Lists including attribute lists are parsed and rendered, empty text renders empty; invalid/reserved record codes are rejected. | MC-NBFX 2.2.3.19 / .20 |
| XML parsing | Strict XML parser, with namespace-aware type mapping; DTD and processing instructions explicitly rejected. | XML 1.0, MC-NBFX supported records |

## Compatibility changes

- **Text is the only implicit value type.** The former heuristic typing
  behavior was deliberately removed, not kept as a legacy fallback.
- `print_records()` now prints text-equivalent XML with no additional
  indentation/whitespace. Existing consumers that relied on pretty formatting
  should adjust their display layer.
- The revised XML parser is strict and targets Python 3.8+.
- `dump_records()` may reject invalid/reserved input that the old parser skipped.
- The original WCF-to-binary binary record types are preserved in the tree,
  but **converting only the rendered XML back to NBFX cannot recreate the
  original binary record types** without a type map or the original record tree.

## Tests run

- `python -m tests.alltests`: original regression/doctest coverage plus new
  tests in `tests/test_conformance.py`.
- CLI: `python xml2wcf.py example.xml` then `python wcf2xml.py`.
- Extra fixture checks for bytes from Microsoft MC-NBFX and the repository's
  sample `example.bin`; all reported separately from interoperability tests.

## Known limitations / follow-up work

1. A WCF transport endpoint, MC-NMF framing and negotiation, and WSDL-based
   SOAP operations are not implemented. This is a **document codec**, not a
   complete WCF client/server stack.
2. No runtime interop tests with an actual .NET WCF service/PowerShell were
   available in this environment. Passing local tests does **not** establish
   full wire compatibility for every WCF service and message.
3. XML exported from NBFX preserves character meaning, not the original
   lexical XML bytes, entity spelling or self-closing syntax. Binary record
   types and exact end-element style are retained only if you keep the in-memory
   tree. A long-lived typed XML interchange format would need metadata.
4. Service-specific requirements for choosing typed records must come from
   that service's WSDL/XSD or empirical interop tests; MC-NBFX permits text but
   does not guarantee that every implementation accepts every equivalent form.
5. Additional fuzzing, malformed-stream limits, and coverage for exotic
   combinations of records remain to be done before treating input as fully
   untrusted or production-critical.

## Official specifications

- [MC-NBFX](https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfx/94c66ea1-e79a-4364-af88-1fa7fef2cc33)
- [MC-NBFX MultiByteInt31](https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfx/1dddf488-1aaa-48c7-bfde-5cb30982ec3c)
- [MC-NBFX TimeSpanText](https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfx/f9b73b93-6974-43ae-9c4c-7b9f82f41b00)
- [MC-NBFX DateTimeText](https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfx/ee19ae39-f21d-4776-ada3-fb0f804b044c)
- [MC-NBFX Array](https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfx/e0cd55a8-016d-4bb7-924e-a8b7add5d52b)
- [MC-NBFS static dictionary](https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfs/9268bb11-94bf-451a-8827-955495e99c7b)
- [MC-NBFSE session dictionary](https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-nbfse/a161304c-1a8a-4f31-beec-b96ebc9b1919)
- [Original GitHub issue #15](https://github.com/ernw/python-wcfbin/issues/15)

## Follow-up review (2026-10-23)

- Implemented **MC-NBFSE** document StringTables in `wcf/session.py`.
  Empty or nonempty per-document tables, session reuse of odd IDs, duplicate
  rejection, unknown-ID rejection, 16 MiB document cap (configurable),
  per-session dictionary limits, atomic state update and session reset.
  The static dictionary remains separate and session resolution is scoped
  using `contextvars`.
- MC-NBFSE encoding now reuses dictionary text values as `DictionaryText`
  when possible, without guessing numeric/boolean types. Explicit path-based
  type overrides take precedence.
- Fixed a validation bug causing valid attribute values to be mistaken for
  dictionary indices because Python strings have a method named `index`.
- Enforced Microsoft MC-NBFX 2.1.2 *canonical* MultiByteInt31 packet lengths,
  rejected unpaired `EndListText` records and invalid DateTime encodings.
- Included a regression vector derived from the exact Microsoft MC-NBFS
  section 3 and MC-NBFSE section 3 SOAP example (action=1, Inventory=3).
- Local suite: **158 tests, 158 passed** on Python 3.13. This includes 500
  deterministic round trips and 4,000 fuzz-like malformed byte-stream inputs.
- The CLI handles one MC-NBFSE document per invocation, not multiple framed
  documents in one session. Use the `BinaryXmlSession` API for streams of
  documents. Real .NET WCF/PowerShell interop was not runnable here because
  neither dotnet/mono/pwsh nor an accessible WCF endpoint was present.

See `MICROSOFT_REVIEW.md` for verified results and outstanding caveats.

## Independent audit fixes (2026-10-23, post2)

- MC-NBFX 2.2.3.9 and 2.2.3.10: FloatText/DoubleText now emit the shortest
  bit-preserving decimal representation, including mandatory uppercase `E`,
  explicit exponent sign, `NaN`, `INF`, `-INF` and `-0`. Float32 is rounded to
  its **actual 32-bit** IEEE 754 representation before being formatted.
- MC-NBFX 2.2.2: every attribute parser and serializer checks that the value
  is a valid Text record (not an Element, Attribute or standalone EndListText).
- MC-NBFX 2.2.1/2.2.2: element/attribute names and prefixes are checked for
  nonempty values and the forbidden `xmlns` name, including session-dictionary
  references. The serializer validates again after object mutation.
- MC-NBFX 2.2.3.15 and 2.2.3.18: Chars32/Bytes32 Length is checked as a
  **positive, signed INT32** when encoding and decoding.
- MC-NBFX 2.2.3.29: fixed UnicodeChars32Text to use **MultiByteInt31** for
  its byte length instead of a fixed 32-bit integer.
- The original suite now includes all 14 independent-audit tests plus 13 new
  boundary tests, including 5,000 seeded IEEE 754 round-trips; `tests.alltests`
  exits with a failure status on test failure.
- **185 tests passing locally**; successful .NET WCF/PowerShell live
  interoperability remains **unverified**. See `CORRECTIONS_CONTRE_AUDIT.md`.
