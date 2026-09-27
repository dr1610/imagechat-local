import sys
from pathlib import Path
import importlib.metadata
if '--dependency' in sys.argv:
    try:sys.exit(0 if importlib.metadata.version('Pillow')=='12.3.0' else 1)
    except importlib.metadata.PackageNotFoundError:sys.exit(1)
root=Path(sys.argv[1]).resolve()
assert Path(sys.prefix).resolve()==root and sys.prefix!=sys.base_prefix
assert 'include-system-site-packages = false' in (root/'pyvenv.cfg').read_text(encoding='utf-8').lower()
