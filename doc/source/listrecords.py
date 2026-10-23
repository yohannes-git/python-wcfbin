"""Write record_list.rst: the record types and their constructors."""

import inspect
import os.path
import sys

sys.path.insert(0, os.path.abspath('..'))

import wcf.records  # noqa: E402

with open('record_list.rst', 'w') as fp:
    fp.write('Available Records\n-----------------\n')
    fp.write('==== =====\nType Class\n==== =====\n')
    for cls in sorted(wcf.records.Record.records.values(),
                      key=lambda cls: cls.type):
        signature = inspect.signature(cls.__init__)
        params = list(signature.parameters.values())[1:]  # without self
        fp.write('0x{0:02X} {1}({2})\n'.format(
            cls.type, cls.__name__,
            ', '.join(str(p).replace('*', '\\*') for p in params)))
    fp.write('==== =====\n')
