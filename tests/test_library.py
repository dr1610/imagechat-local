import unittest,tempfile,io,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from core import Store
from image_library import ImageLibrary

class LibraryTest(unittest.TestCase):
 def test_provenance_favorites_and_missing(self):
  with tempfile.TemporaryDirectory() as d:
   s=Store(d);lib=ImageLibrary(s)
   a=s.create_session('A');b=s.create_session('B');buf=io.BytesIO();Image.new('RGB',(16,16),'red').save(buf,format='PNG')
   source=s.add_image(buf.getvalue(),'添付');output=s.add_image(buf.getvalue(),'生成')
   g=dict(id='g',session_id=a['id'],created=1,status='Completed',original_prompt='赤い服',enhanced_prompt='red outfit',prompt='red outfit',outputs=[output],references=[source['id']])
   s.save_generation(g);s.update_session(b['id'],{'draft':{'references':[output['id']]}})
   items={i['id']:i for i in lib.list()['items']}
   self.assertEqual(len(items),2);self.assertEqual(items[output['id']]['kind'],'generated');self.assertEqual(items[output['id']]['contexts'][0]['prompt'],'赤い服')
   self.assertEqual(items[source['id']]['contexts'][0]['role'],'input')
   before=s.generation('g');lib.favorite({'asset_id':output['id'],'favorite':True});s.db.close()
   s=Store(d);lib=ImageLibrary(s);self.assertTrue(next(i for i in lib.list()['items'] if i['id']==output['id'])['favorite']);self.assertEqual(s.generation('g'),before)
   s.asset_path(source['id']).unlink();self.assertTrue(next(i for i in lib.list()['items'] if i['id']==source['id'])['missing'])
   lib.favorite({'asset_id':output['id'],'favorite':False});self.assertFalse(next(i for i in lib.list()['items'] if i['id']==output['id'])['favorite']);s.db.close()

if __name__=='__main__':unittest.main()
