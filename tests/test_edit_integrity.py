import tempfile,unittest,sys,io
from PIL import Image
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import Application,AppError
from style_prompt import apply_style
from reference_input import validate_reference_mentions

class EditIntegrity(unittest.TestCase):
    def test_numbered_references(self):
        for p in ['２枚目のポーズに','<image2>を参考に','＜ｉｍａｇｅ２＞を参考に']:
            with self.assertRaises(AppError):validate_reference_mentions(p,['a'])
            validate_reference_mentions(p,['a','b'])
        validate_reference_mentions('赤い服に変更', ['a'])

    def test_generation_uses_exact_edit_text(self):
        with tempfile.TemporaryDirectory() as d:
            app=Application(d);app.start=lambda *a:None
            s=app.store.create_session('test')
            buf=io.BytesIO();Image.new('RGB',(64,64),'red').save(buf,format='PNG')
            a=app.store.add_image(buf.getvalue())
            for model in ['official','noct_anime']:
                g=app.generate(dict(session_id=s['id'],prompt='ジャケットを青に変更',references=[a['id']],params=dict(art_style='illustration',model_preset=model)))
                self.assertEqual(g['prompt'],'ジャケットを青に変更');self.assertEqual(g['style_instruction'],'')
            with self.assertRaises(AppError):app.generate(dict(session_id=s['id'],prompt='2枚目のポーズに',references=[a['id']]))
            app.store.db.close()
            for handler in list(app.logger.handlers):
                handler.close();app.logger.removeHandler(handler)

    def test_t2i_style_still_available(self):
        self.assertNotEqual(apply_style('猫','illustration')[0],'猫')
        self.assertEqual(apply_style('猫','illustration',editing=True),('猫',''))

if __name__=='__main__':unittest.main()
