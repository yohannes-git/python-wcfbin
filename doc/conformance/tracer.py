"""Run the repository suite and record, per test, the MC-NBFX record types
decoded (registry lookups) and encoded (to_bytes)."""
import json, sys, os, unittest, collections
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT = sys.argv[1]
sys.path.insert(0, REPO)
os.chdir(REPO)
import wcf.records as R
from wcf.records import base

current = ['<import>']
decoded = collections.defaultdict(set)
encoded = collections.defaultdict(set)

class LoggingDict(dict):
    _last_none = None
    def get(self, k, default=None):
        v = dict.get(self, k, default)
        if isinstance(k, int):
            if self._last_none is not None and k == self._last_none - 1:
                self._last_none = None   # *WithEndElement second lookup
            else:
                decoded[current[0]].add(k)
                self._last_none = k if v is None else None
        return v
    def __getitem__(self, k):
        v = dict.__getitem__(self, k)
        decoded[current[0]].add(k + 1)  # array item class lookup
        return v

base.Record.records = LoggingDict(base.Record.records)
def _prof(frame, event, arg):
    if event == 'call' and frame.f_code.co_name == 'parse':
        cls = frame.f_locals.get('cls')
        if isinstance(cls, type) and issubclass(cls, base.Record) and cls is not base.Record:
            decoded[current[0]].add(cls.type)
    if event == 'return' and frame.f_code.co_name == 'to_bytes':
        self = frame.f_locals.get('self')
        if isinstance(self, base.Record) and isinstance(arg, (bytes, bytearray)) and arg:
            encoded[current[0]].add(arg[0])
sys.setprofile(_prof)

orig_dump = R.dump_records
def dump_records(records):
    out = orig_dump(records)
    # odd types written by dump_records: rescan cheaply via a re-parse
    try:
        import io
        saved = current[0]
        current[0] = saved + '#dump'
        base.Record.parse(io.BytesIO(out), R.NO_QUOTAS)
    except Exception:
        pass
    finally:
        current[0] = saved
    return out
R.dump_records = dump_records

class Result(unittest.TextTestResult):
    def startTest(self, test):
        current[0] = test.id()
        super().startTest(test)

suite = unittest.defaultTestLoader.discover('tests', top_level_dir='.')
runner = unittest.TextTestRunner(resultclass=Result, verbosity=0, stream=open(os.devnull, 'w'))
res = runner.run(suite)
print('ran', res.testsRun, 'fail', len(res.failures), 'err', len(res.errors))
out = {}
for t in set(decoded) | set(encoded):
    out[t] = {'dec': sorted(decoded.get(t, ())), 'enc': sorted(encoded.get(t, ()))}
json.dump(out, open(OUTPUT, 'w'), indent=0)
