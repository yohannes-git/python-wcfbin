"""Helpers shared by the tests."""

import os
import subprocess
import sys

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_python(code, **env):
    """Run code in a new interpreter that imports this checkout of wcf,
    with extra environment variables (e.g. TZ); returns its stdout."""
    environment = dict(os.environ, **env)
    environment['PYTHONPATH'] = os.pathsep.join(
        [TOP] + [p for p in environment.get('PYTHONPATH', '').split(os.pathsep) if p])
    return subprocess.run([sys.executable, '-c', code], capture_output=True,
                          check=True, env=environment).stdout.decode()


def local_times(tz, values):
    """str() of local DateTimeText records on a host in the fixed-offset
    time zone ``tz`` (POSIX TZ: "XST-02" is +02:00), the name of the
    exception for a refused value."""
    code = ('from wcf.records import DatetimeTextRecord\n'
            'for v in %r:\n'
            '    try: print(DatetimeTextRecord(v, 2))\n'
            '    except ValueError as e: print(type(e).__name__)' % (values,))
    return run_python(code, TZ=tz).split()
