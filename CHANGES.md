Changes
=======

0.6.0
-----

Conformity work (MC-NBFX, MC-NBFS, MC-NBFSE), then a review for
conformity, security, code quality and performance.

Behaviour changes:

* XML to binary writes values as text (`Chars*Text`; `BinaryXmlSession`
  writes a string of its dictionaries as a `DictionaryText`); typed records
  only through an explicit type map (`8.0` is no longer re-typed as a
  double).
* `str()` of the text records is the characters they represent, unescaped;
  `render_xml()` escapes (MC-NBFX 2.2.3.13.1) and refuses names and comments
  that XML cannot carry.
* TimeSpanText is rendered as an xsd:duration, DateTimeText always with its
  time, FloatText/DoubleText with the shortest round-trip digits and `0.5`
  rather than `5E-1`, DecimalText with its scale (`1.50`) and `-0` as `0`,
  a local DateTimeText from its UTC ticks as .NET writes them.
* UnicodeChars32Text has a 4-byte INT32 length.
* Every data error raises `wcf.errors.WcfBinaryError` (a `ValueError`);
  constructors refuse extra arguments and values of the wrong type
  (`TypeError`).
* `Record.parse()` applies decoding quotas (`Quotas`, `DEFAULT_QUOTAS`).
* Python 3.8 or later; the `future` dependency and the Python 2 code are
  gone; the library no longer configures logging when imported.
* `proxy.py` and `WcfPlugin.py` are removed: Python 2 tools (an HTTP
  proxy and a Jython plugin for Burp) that the Python 3 library cannot
  serve; `wcf2xml.py` and `xml2wcf.py` remain.

New:

* `wcf.session.BinaryXmlSession`: MC-NBFSE StringTables (session
  dictionary with odd ids), bounded, kept for the following documents.
  After a refused StringTable it is `out_of_step` and refuses every
  document until `reset()`.
* `wcf.records.Quotas`, `DEFAULT_QUOTAS`, `NO_QUOTAS`.
* `wcf.errors.WcfBinaryError`, `wcf.dictionary.UnknownDictionaryId`.
* `wcf.xmltext`: XML names, escaping and comments.
* `wcf.datatypes.Decimal.from_string()`.
* `wcf2xml.py --no-quotas`; `--nbfse` for both scripts.

See README.md for the deviations from the text of the specification.
