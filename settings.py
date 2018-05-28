import sys
import os

DISKS = ['sda3']
NETWORK_INTERFACES = ['eth0']
HOST = "127.0.0.1"
PORT = 8090
DEBUG = False
ROOT_PATH = os.path.dirname(__file__)

_settings_local_pathes = [
    os.path.join(ROOT_PATH, 'settings_local.py'),
]

for s in sys.argv:
    if s.startswith("--settings="):
        _settings_local_pathes.append(
            s.split("=")[1]
        )

for p in _settings_local_pathes:
    if p and os.path.exists(p):
        with open(p) as f:
            code = compile(f.read(), os.path.basename(p), 'exec')
            exec(code, globals(), locals())
            sys.stdout.write("settings_local: %s has been applied.\n" % p)
        break
else:
    sys.stderr.write('\nWARNING!!! settings_local was not found. Discovery path: \n  ->  %s' % ("\n  ->  ".join(_settings_local_pathes)))
