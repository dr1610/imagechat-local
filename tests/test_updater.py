import hashlib,json,tempfile,unittest,zipfile
from pathlib import Path
from updater import prepare,version,safe_name
from update_worker import transact

class Updates(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);(self.root/'a.py').write_text('old')
  (self.root/'update-baseline.json').write_text(json.dumps({'a.py':hashlib.sha256(b'old').hexdigest()}))
 def package(self,files=None):
  files=files or {'a.py':b'new'};archive=self.root/'test.zip'
  with zipfile.ZipFile(archive,'w') as z:
   for name,content in files.items():z.writestr(name,content)
   z.writestr('update-manifest.json',json.dumps({'protocol':1,'version':'0.1.3-beta','files':{n:hashlib.sha256(c).hexdigest() for n,c in files.items()}}))
  return archive
 def test_prepare_no_installed_write(self):
  changes=prepare(self.root,self.package(),self.root/'stage','v0.1.3-beta')
  self.assertEqual((self.root/'a.py').read_text(),'old');self.assertIn('a.py',changes)
 def test_local_edits_block(self):
  (self.root/'a.py').write_text('custom')
  with self.assertRaisesRegex(ValueError,'ローカル変更'):prepare(self.root,self.package(),self.root/'stage','v0.1.3-beta')
  self.assertFalse((self.root/'stage').exists())
 def test_unchanged_upstream_preserves_customization(self):
  (self.root/'a.py').write_text('custom')
  changes=prepare(self.root,self.package({'a.py':b'old'}),self.root/'stage','v0.1.3-beta')
  self.assertNotIn('a.py',changes)
  self.assertEqual((self.root/'a.py').read_text(),'custom')
 def test_path_protection(self):
  for name in ['../bad.py','D:/bad.py','data/settings.json','models/m.json','.venv/a.py','public/../../a.py','public\\a.js','/a.py']:
   with self.subTest(name=name),self.assertRaises(ValueError):safe_name(name)
 def test_corrupt_hash(self):
  archive=self.package()
  with zipfile.ZipFile(archive,'a') as z:z.writestr('a.py',b'bad')
  with self.assertRaises(ValueError):prepare(self.root,archive,self.root/'stage','v0.1.3-beta')
 def test_wrong_version(self):
  with self.assertRaises(ValueError):prepare(self.root,self.package(),self.root/'stage','v0.1.4-beta')
 def test_success_preserves_data(self):
  (self.root/'data').mkdir();(self.root/'data/image.png').write_bytes(b'image')
  changes=prepare(self.root,self.package(),self.root/'stage','v0.1.3-beta')
  self.assertTrue(transact(self.root,self.root/'stage',self.root/'backup',changes,lambda:None,lambda c:True))
  self.assertEqual((self.root/'a.py').read_text(),'new');self.assertEqual((self.root/'backup/a.py').read_text(),'old')
  self.assertEqual((self.root/'data/image.png').read_bytes(),b'image')
 def test_failed_boot_restores_old_and_removes_new(self):
  changes=prepare(self.root,self.package({'a.py':b'new','new.py':b'new'}),self.root/'stage','v0.1.3-beta')
  with self.assertRaises(RuntimeError):transact(self.root,self.root/'stage',self.root/'backup',changes,lambda:None,lambda c:False)
  self.assertEqual((self.root/'a.py').read_text(),'old');self.assertFalse((self.root/'new.py').exists())
 def test_version_order(self):
  self.assertGreater(version('v0.1.12-beta'),version('0.1.2-beta'))
  self.assertGreater(version('0.1.2'),version('0.1.2-beta'))

if __name__=='__main__':unittest.main()
