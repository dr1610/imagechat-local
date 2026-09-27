import unittest,sys,copy,tempfile,io
from PIL import Image
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import Application,PARAMS
from edit_policy import plan
from model_routing import resolve
from comfy import AppError

MASK={'width':768,'height':768,'strokes':[{'layer':'mask','points':[[378,185],[378,280]],'size':110}],'poses':[]}
class PolicyTest(unittest.TestCase):
 def p(self,**kw):return {**PARAMS,'art_style':'illustration',**kw}
 def test_auto_cases(self):
  for text,n,expected in [('１枚目を２枚目のポーズに',2,True),('人物を入れ替えて',2,True),('上から見下ろして',1,True),('下から見上げて',1,True),('猫を追加',1,False),('後ろから',1,False),('顔のアップ',1,False),('教室を描いて',0,False)]:
   with self.subTest(text=text):self.assertEqual(plan(text,['a']*n,self.p())['use_enhancer'],expected)
 def test_mode_boundaries(self):
  self.assertFalse(plan('下から見上げて',['a'],self.p(enhancer='off'))['use_enhancer'])
  self.assertTrue(plan('猫を追加',['a'],self.p(enhancer='local'))['use_enhancer'])
  self.assertFalse(plan('下から見上げて',['a'],self.p(),MASK)['use_enhancer'])
  self.assertFalse(plan('下から見上げて',['a'],self.p(art_style='photoreal'))['use_enhancer'])
 def test_edit_and_t2i(self):
  p=self.p();self.assertEqual(resolve(p,None,{},editing=True)['id'],'official');self.assertEqual(p['cfg'],3)
  p=self.p();self.assertEqual(resolve(p,None,{},editing=False)['id'],'official')
 def test_mask_strength(self):
  p=self.p();resolve(p,MASK,{},editing=True,prompt='マスクした部分を青に変更して');self.assertEqual(p['control_strength'],.5)
  p=self.p();resolve(p,MASK,{},editing=True,prompt='白い星を追加');self.assertEqual(p['control_strength'],1)
  p=self.p(control_strength=.5);resolve(p,{'poses':[{}]}, {},editing=True,prompt='青に変更');self.assertEqual(p['control_strength'],1)
 def test_manual(self):
  p=self.p(sampling_policy='manual',cfg=1.7,control_strength=.8);resolve(p,MASK,{},editing=True,prompt='青に変更');self.assertEqual((p['cfg'],p['control_strength']),(1.7,.8))
 def test_old_regenerate(self):
  original=self.p(model_preset='noct_anime');selection=resolve(original,None,{},editing=False)
  original['model_preset']='auto' # Recorded history from the earlier catalog.
  prior={'params':original,'model_selection':selection}
  p=copy.deepcopy(original);result=resolve(p,None,{},prior=prior,editing=True)
  self.assertEqual(result['id'],'noct_anime');self.assertEqual(p,original)
 def test_metadata_and_no_silent_fallback(self):
  with tempfile.TemporaryDirectory() as d:
   app=Application(Path(d));app.start=lambda *args:None
   sid=app.store.create_session()['id']
   buffer=io.BytesIO();Image.new('RGB',(64,64),'white').save(buffer,format='PNG')
   a=app.store.add_image(buffer.getvalue())['id']
   body=dict(session_id=sid,prompt='下から見上げて',references=[a],params=self.p())
   with self.assertRaises(AppError):app.generate(body)
   body['prompt']='両手を上げて';g=app.generate(body)
   self.assertEqual(g['model_selection']['id'],'official');self.assertEqual(g['params']['cfg'],3)
   self.assertEqual(g['prompt'],body['prompt']);self.assertFalse(g['edit_policy']['use_enhancer'])
   body.update(prompt='マスクした部分を青に変更して',editor=MASK);g=app.generate(body)
   self.assertEqual(g['params']['control_strength'],.5)
   app.stopping.set();app.store.db.close()
   for handler in list(app.logger.handlers):handler.close();app.logger.removeHandler(handler)
if __name__=='__main__':unittest.main()
