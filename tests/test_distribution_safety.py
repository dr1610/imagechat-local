import unittest,tempfile,sys,subprocess,socket
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime_lock import DataLock
from import_data import migrate
ROOT=Path(__file__).resolve().parents[1]

class DistributionSafety(unittest.TestCase):
    def test_data_lock_rejects_second_holder(self):
        with tempfile.TemporaryDirectory() as d:
            first=DataLock(d)
            try:
                with self.assertRaises(RuntimeError):DataLock(d)
            finally:first.close()
            second=DataLock(d);second.close()
    def test_copy_preserves_source_and_rejects_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            old=Path(d)/'old';new=Path(d)/'new';new.mkdir()
            lock=DataLock(old/'data');lock.close()
            sample=old/'data'/'settings.json';sample.write_bytes(b'{"keep":true}')
            migrate(old,new)
            self.assertEqual(sample.read_bytes(),(new/'data'/'settings.json').read_bytes())
            with self.assertRaises(ValueError):migrate(old,new)
            self.assertEqual(sample.read_bytes(),b'{"keep":true}')
    def test_running_source_not_copied(self):
        with tempfile.TemporaryDirectory() as d:
            old=Path(d)/'old';new=Path(d)/'new';new.mkdir();lock=DataLock(old/'data')
            try:
                with self.assertRaises(RuntimeError):migrate(old,new)
                self.assertFalse((new/'data').exists())
            finally:lock.close()
    def test_non_http_listener_blocks_launcher(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));s.listen()
            result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'Start.ps1'),'-NoBrowser','-Port',str(s.getsockname()[1])],capture_output=True,timeout=20)
            self.assertNotEqual(result.returncode,0)
            self.assertIn(b'already in use',result.stderr)
    def test_base_python_is_rejected(self):
        import sysconfig
        base=Path(sys.base_prefix)/'python.exe'
        result=subprocess.run([str(base),'-I',str(ROOT/'environment_check.py'),sys.base_prefix],capture_output=True,timeout=10)
        self.assertNotEqual(result.returncode,0)

if __name__=='__main__':unittest.main()
