#!/bin/sh
# Rebuild doc/CONFORMANCE.md: run the test suite to record which record
# types the tests other than the traceability tests decode and encode,
# then check the traceability tests against the statuses of catalog.py.
set -e
cd "$(dirname "$0")"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
python3 tracer.py "$tmp/trace.json"
python3 - "$tmp/trace.json" "$tmp/rt_evidence.json" <<'PY'
import collections, json, sys
d = json.load(open(sys.argv[1]))
# the traceability tests prove each record type themselves; random inputs
# do not prove anything about a given type
EXCL = ('test_spec_traceability', 'test_fuzz_random', 'test_mutated_input',
        'test_truncated_input', 'test_random_xml_conversion')
dec = collections.defaultdict(set); enc = collections.defaultdict(set)
for t, v in d.items():
    if any(x in t for x in EXCL): continue
    base = t.replace('#dump', '')
    for k in v['dec']:
        (enc if t.endswith('#dump') else dec)[k].add(base)
    for k in v['enc']:
        enc[k].add(base)
json.dump({'dec': {k: sorted(v) for k, v in dec.items()}, 'enc': {k: sorted(v) for k, v in enc.items()}},
          open(sys.argv[2], 'w'), indent=0)
PY
python3 gen_matrix.py "$tmp/rt_evidence.json"
