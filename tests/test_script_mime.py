"""Regression: incorrect Windows MIME associations must not break the UI."""
import json
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class ScriptMime(unittest.TestCase):
    def test_javascript_http_headers_override_os_associations(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            (data / 'update-settings.json').write_text('{"automatic":false}')
            code = (
                "import mimetypes;"
                "mimetypes.add_type('text/plain','.mjs');"
                "mimetypes.add_type('application/octet-stream','.js');"
                "import server;server.serve(port=8799,data_root=" + repr(str(data)) + ")"
            )
            child = subprocess.Popen([sys.executable, '-B', '-c', code], cwd=ROOT,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                for _ in range(100):
                    if child.poll() is not None:
                        self.fail(child.stderr.read().decode(errors='replace'))
                    try:
                        with urllib.request.urlopen('http://127.0.0.1:8799/api/bootstrap', timeout=1) as r:
                            boot = json.load(r)
                        break
                    except OSError:
                        time.sleep(.1)
                else:
                    self.fail('Test server did not start')
                for name in ('pose-geometry.mjs', 'app.js'):
                    with self.subTest(name=name), urllib.request.urlopen('http://127.0.0.1:8799/' + name) as r:
                        self.assertEqual(r.headers.get_content_type(), 'text/javascript')
                        self.assertTrue(r.read())
                request = urllib.request.Request('http://127.0.0.1:8799/api/shutdown', data=b'{}',
                    headers={'X-QIC-Token': boot['token'], 'Content-Type': 'application/json'})
                urllib.request.urlopen(request).close()
                child.wait(timeout=10)
            finally:
                if child.poll() is None:
                    child.terminate(); child.wait(timeout=10)
                child.stderr.close()
