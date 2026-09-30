import io
import tempfile
import unittest

from PIL import Image

from core import AppError, Application, Workflows


class LocalComfyStub:
    def __init__(self):
        workflow = Workflows().select('move')
        self.info = {node['class_type']: {} for node in workflow['graph'].values()}
        self.info['LoadImage'] = {}
        self.info['UNETLoader'] = {'input': {'required': {'unet_name': [['qwen_image_2.1_test.safetensors']]}}}
        self.info['CLIPLoader'] = {'input': {'required': {'clip_name': [['qwen3vl_test.safetensors']]}}}
        self.info['VAELoader'] = {'input': {'required': {'vae_name': [['qwen_image_2.1_test.safetensors']]}}}

    def request(self, path, timeout=None):
        self.last_path = path
        return self.info

    def upload(self, path):
        return path.name


class MoveRequestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Application(self.temp.name)
        self.app.start = lambda *args: None
        self.session = self.app.store.create_session('move')
        self.comfy = LocalComfyStub()
        self.assets = []
        for color in ('blue', 'yellow'):
            image = io.BytesIO()
            Image.new('RGB', (128, 128), color).save(image, format='PNG')
            self.assets.append(self.app.store.add_image(image.getvalue())['id'])

    def tearDown(self):
        self.app.store.db.close()
        for handler in list(self.app.logger.handlers):
            handler.close()
            self.app.logger.removeHandler(handler)
        self.temp.cleanup()

    def prepare(self, refs, source_image, source=None, target=None):
        editor = {'width': 128, 'height': 128, 'x': 0, 'y': 0, 'strokes': [], 'poses': [],
                  'move': {'source_image': source_image, 'source': source or [8, 8, 40, 40],
                           'target': target or [72, 72, 104, 104]}}
        g = self.app.generate({'session_id': self.session['id'], 'prompt': '移動して',
                               'references': refs, 'editor': editor,
                               'params': {'enhancer': 'off'}})
        g['model_config'] = {'model': 'qwen_image_2.1_test.safetensors',
                             'text_encoder': 'qwen3vl_test.safetensors',
                             'vae': 'qwen_image_2.1_test.safetensors',
                             'control_model': ''}
        return self.app.prepare(g, self.comfy)

    def test_one_image_move_uses_one_marked_reference(self):
        result = self.prepare(self.assets[:1], 1)
        self.assertEqual(result['intent'], 'move')
        self.assertEqual(result['workflow_id'], 'qwen21_move')
        self.assertEqual(result['features'], ['move'])
        self.assertEqual(result['workflow']['4']['inputs']['images.image_1'], ['ref_1', 0])
        self.assertIn('red bounding box', result['effective_parameters']['prompt'])
        self.assertEqual(self.comfy.last_path, '/object_info')

    def test_two_image_move_binds_both_references(self):
        result = self.prepare(self.assets, 2)
        self.assertEqual(result['intent'], 'move')
        self.assertEqual(result['workflow']['4']['inputs']['images.image_2'], ['ref_2', 0])
        self.assertIn('<image2>', result['effective_parameters']['prompt'])
        self.assertIn('move_source_base', result['files'])

    def test_invalid_source_is_rejected(self):
        with self.assertRaises(AppError) as error:
            self.prepare(self.assets[:1], 2)
        self.assertEqual(error.exception.category, 'Move')


if __name__ == '__main__':
    unittest.main()
