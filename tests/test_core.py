import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import Store, Workflows, AppError, dimensions, expansion, parse_expand, render_editor, uid, now
from comfy import local_url
from enhancer import enhance


class Invariants(unittest.TestCase):
    def test_enhancer_off_keeps_original_exactly(self):
        text='  この子を学校の廊下で歩かせて。横から\n'
        result=enhance(text)
        self.assertEqual(result.original,text);self.assertEqual(result.effective,text);self.assertIsNone(result.enhanced)
        with self.assertRaises(AppError):enhance(text,'external')

    def test_local_only(self):
        for url in ['https://example.com','http://8.8.8.8:8188','http://localhost.evil.test','http://user:pass@localhost','http://127.0.0.1/other']:
            with self.assertRaises(AppError):local_url(url)
        self.assertEqual(local_url('http://127.0.0.1:8188'),'http://127.0.0.1:8188')

    def test_exact_aspects(self):
        for ratio in ['1:1','4:3','3:4','16:9','9:16']:
            w,h=dimensions(ratio,768);a,b=map(int,ratio.split(':'))
            self.assertEqual(w*b,h*a);self.assertEqual(w%32,0);self.assertEqual(h%32,0)

    def test_non_destructive_expansion(self):
        e=expansion((384,640),'16:9','left')
        self.assertEqual(e['width']*9,e['height']*16);self.assertEqual(e['x'],0)
        self.assertGreaterEqual(e['height'],640)
        base=Image.new('RGBA',(384,640),'red');before=base.tobytes()
        canvas,sketch,mask,pose=render_editor(base,e)
        self.assertEqual(base.tobytes(),before);self.assertEqual(canvas.getpixel((e['x']+10,e['y']+10)),(255,0,0,255))
        self.assertIsNone(sketch.getbbox());self.assertIsNone(mask.getbbox())

    def test_layers_and_erase_are_independent(self):
        base=Image.new('RGB',(128,128),'white')
        strokes=[dict(layer='sketch',points=[[30,30],[100,30]],size=10,color='#ff0000'),dict(layer='mask',points=[[30,70],[100,70]],size=10),dict(layer='sketch',erase=True,points=[[50,20],[50,40]],size=12)]
        canvas,sketch,mask,_=render_editor(base,dict(width=128,height=128,strokes=strokes))
        self.assertEqual(canvas.getpixel((40,30)),(255,255,255,255))
        self.assertEqual(sketch.getpixel((40,30)),(255,0,0,255));self.assertEqual(sketch.getpixel((50,30))[3],0)
        self.assertEqual(mask.getpixel((50,70)),255);self.assertEqual(mask.getpixel((50,30)),0)

    def test_expand_preserves_partial_alpha_and_rgb(self):
        base=Image.new('RGBA',(64,96),(50,100,150,120))
        canvas,sketch,_,_=render_editor(base,dict(width=192,height=128,x=64,y=16))
        self.assertEqual(canvas.crop((64,16,128,112)).tobytes(),base.tobytes())
        composite=Image.alpha_composite(canvas,sketch)
        self.assertEqual(composite.crop((64,16,128,112)).tobytes(),base.tobytes())

    def test_natural_expand(self):
        e=parse_expand('16:9にして、人物はそのままで左右の背景を広げて',(384,640))
        self.assertEqual(e['width']*9,e['height']*16)
        e=parse_expand('下方向だけ続きを描いて',(640,480));self.assertEqual(e['y'],0)
        self.assertIsNone(parse_expand('夜に変更してください',(640,480)))

    def test_external_workflow_bindings(self):
        w=Workflows();profile=w.select('multi_reference')
        values=dict(model='m',text_encoder='t',vae='v',prompt='日本語の原文',negative_prompt='',width=640,height=480,seed=9,steps=25,cfg=1,sampler='euler',scheduler='simple',denoise=1,output_prefix='test')
        graph=w.build(profile,values,['one.png','two.png'],[])
        self.assertEqual(graph['4']['inputs']['prompt'],'日本語の原文')
        self.assertEqual(graph['4']['inputs']['images.image_1'],['ref_1',0]);self.assertEqual(graph['ref_2']['inputs']['image'],'two.png')
        with self.assertRaises(AppError):w.build(w.select('t2i'),values,['one.png'],['mask'])

    def test_store_restart_tree_and_alpha(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(tmp);a=s.create_session('A');b=s.create_session('B');ids=[uid() for _ in range(4)]
            for i,parent in enumerate([None,ids[0],ids[0],ids[1]]):
                s.save_generation(dict(id=ids[i],session_id=a['id'],created=now(),status='Completed',parent_generation_id=parent,original_prompt='原文',outputs=[]))
            image=Image.new('RGBA',(64,64),(255,0,0,80));buf=io.BytesIO();image.save(buf,format='PNG');asset=s.add_image(buf.getvalue())
            s.update_session(a['id'],{'draft':{'editor':{'poses':[{'points':[[1,2]]*18}],'strokes':[]}}});s.db.close()
            reopened=Store(tmp);gens=reopened.session(a['id'])['generations']
            self.assertEqual([g['parent_generation_id'] for g in gens],[None,ids[0],ids[0],ids[1]])
            self.assertEqual(reopened.session(b['id'])['generations'],[])
            with Image.open(reopened.asset_path(asset['id'])) as out:self.assertEqual(out.getpixel((0,0))[3],80)
            self.assertEqual(len(reopened.session(a['id'])['draft']['editor']['poses']),1);reopened.db.close()

    def test_corrupt_image_does_not_damage_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(tmp)
            with self.assertRaises(AppError):s.add_image(b'not an image')
            self.assertEqual(s.create_session('usable')['title'],'usable');s.db.close()


if __name__=='__main__':unittest.main()
