"""Exercise media CLI contracts offline; live providers are checked separately.

API responses are fixtures, downloads use a real local HTTP server. No provider
credentials or network availability are needed for regression tests.
"""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
import zlib
import struct

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/curate-media.mjs'
NODE = shutil.which('node')
FFMPEG = shutil.which('ffmpeg')
FFPROBE = shutil.which('ffprobe')


def png():
    def chunk(name, data):
        return struct.pack('>I', len(data)) + name + data + struct.pack('>I', zlib.crc32(name + data))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 8, 6, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress((b'\0' + bytes([200, 90, 30]) * 8) * 6)) + chunk(b'IEND', b'')


@unittest.skipUnless(NODE, 'Node is required')
class CurateMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = png()
        cls.video_temp = tempfile.TemporaryDirectory(prefix='oil-curate-video-')
        cls.video = None
        if FFMPEG and FFPROBE:
            video = Path(cls.video_temp.name) / 'sample.mp4'
            subprocess.run([FFMPEG, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=64x48:d=0.4', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)], check=True, capture_output=True, timeout=20)
            cls.video = video.read_bytes()
        cls.requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                cls.requests.append(self.path)
                if self.path.startswith('/video') and cls.video:
                    data, mime = cls.video, 'video/mp4'
                elif self.path.startswith('/bad') or '/slideshow/' in self.path:
                    data, mime = b'<html>upstream error</html>', 'text/html'
                elif self.path.startswith('/corrupt'):
                    data, mime = cls.image[:24], 'image/png'
                elif self.path.startswith('/large'):
                    data, mime = cls.image + b'x' * (2 * 1024 * 1024), 'image/png'
                else:
                    data, mime = cls.image, 'image/png'
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', len(data))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            def log_message(self, *_):
                pass
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.video_temp.cleanup()

    def setUp(self):
        # URL metacharacters expose missing path-to-URL conversion on every OS.
        self.temp = tempfile.TemporaryDirectory(prefix='oil-curate-test-中文 #%-')
        self.addCleanup(self.temp.cleanup)
        self.cwd = Path(self.temp.name)
        self.shim = self.cwd / 'fixture.mjs'
        file = {'url': self.base + '/image', 'size': len(self.image), 'md5': hashlib.md5(self.image).hexdigest()}
        self.fixtures = {
            '/assets?t=textures': {'wood': {'name': 'Wood', 'categories': ['wood'], 'authors': {'Artist': 'All'}}},
            '/assets?t=models': {'wood-model': {'name': 'Wood model', 'tags': ['wood']}},
            '/files/wood': {k: {'1k': {'jpg': file}} for k in ('Diffuse', 'Rough', 'nor_gl')},
            '/files/wood-model': {'gltf': {'1k': {'gltf': {'url': self.base + '/model.gltf', 'include': {'model.bin': {'url': self.base + '/model.bin'}}}}}},
            '/v2/objects/search': {'records': [{'systemNumber': 'O1', '_primaryTitle': 'Wood furniture', '_images': {'_iiif_image_base_url': self.base + '/iiif'}}]},
            '/iiif/info.json': {'width': 8, 'height': 6},
            '/catalogue/v2/images': {'results': [{'id': 'im1', 'source': {'id': 'work1', 'title': 'Wood plate'}, 'locations': [{'url': self.base + '/iiif/info.json', 'locationType': {'id': 'iiif-image'}, 'credit': 'Creator / Wellcome', 'license': {'label': 'CC BY 4.0', 'url': 'https://creativecommons.org/licenses/by/4.0/'}}]}]},
            '/photos/': {'results': [{'id': 'http://www.loc.gov/item/1/', 'title': 'Wood photograph', 'image_url': [self.base + '/a.jpg'], 'item': {'rights_advisory': 'Item-specific rights'}}]},
            '/maps/': {'results': [{'id': 'http://www.loc.gov/item/2/', 'title': 'Wood map', 'image_url': [self.base + '/a.jpg']}]},
            '/collections/historic-american-buildings-landscapes-and-engineering-records/': {'results': [
                {'id': 'http://www.loc.gov/item/photo-only/', 'title': 'Not a drawing', 'image_url': [self.base + '/photo.jpg']},
                {'id': 'http://www.loc.gov/item/3/', 'title': 'Wood bridge', 'resources': [{'url': 'https://www.loc.gov/resource/hhh.3.sheet', 'image': self.base + '/sheet/00001_150px.jpg'}]}
            ]},
            '/search': {'collection': {'items': [{'href': self.base + '/manifest', 'data': [{'nasa_id': 'earth', 'title': 'Wood and Earth in orbit', 'media_type': 'image', 'center': 'NASA', 'photographer': 'Photographer'}], 'links': [{'href': self.base + '/thumb', 'render': 'image', 'rel': 'preview'}]}]}},
            '/manifest': [self.base + '/media~orig.jpg'],
            '/w/api.php': {'query': {'pages': [{'pageid': 11, 'index': 1, 'title': 'File:Wood engraving map.jpg', 'imageinfo': [{'url': self.base + '/commons.png', 'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Wood.jpg', 'width': 8, 'height': 6, 'mime': 'image/png', 'extmetadata': {'LicenseShortName': {'value': 'CC BY-SA 4.0'}, 'LicenseUrl': {'value': 'https://creativecommons.org/licenses/by-sa/4.0'}, 'Artist': {'value': '<a href="x">Someone</a>'}}}]}]}},
            '/api/v1/artworks/search': {'config': {'iiif_url': self.base + '/aic'}, 'data': [{'id': 5, 'title': 'Wood box', 'image_id': 'img', 'is_public_domain': True, 'thumbnail': {'width': 8, 'height': 6}}]},
            '/api/artworks/': {'data': [{'id': 7, 'title': 'Wood chest', 'url': 'https://clevelandart.org/art/7', 'images': {'web': {'url': self.base + '/k.png', 'width': '8', 'height': '6'}}}]},
            '/public/collection/v1.1/search': {'objectIDs': [1]},
            '/public/collection/v1/objects/1': {'objectID': 1, 'isPublicDomain': True, 'primaryImage': self.base + '/m.png', 'title': 'Wood chair'},
            '/api/item/search/jps-cross': {'hit': 1, 'list': [{'id': 'cobas-1', 'common': {'id': 'cobas-1', 'title': '木の箱', 'titleEn': '&lt;i&gt;Wood&lt;/i&gt; box', 'contentsRightsType': 'ccby', 'contentsUrl': [self.base + '/media/tnm/1/image/slideshow_s/1.png'], 'thumbnailUrl': [self.base + '/media/tnm/1/image/slideshow_s/1.png'], 'database': 'cobas', 'contributor': ['Tokyo National Museum'], 'linkUrl': 'https://colbase.nich.go.jp/collection_items/tnm/1'}}]},
            '/search/collection': {'orderedItems': [{'id': self.base + '/rk/1'}]},
            '/rk/1': {'id': self.base + '/rk/1', 'identified_by': [{'type': 'Name', 'content': 'Houten stoel'}, {'type': 'Name', 'content': 'Wood chair', 'language': [{'id': 'http://vocab.getty.edu/aat/300388277'}]}, {'type': 'Identifier', 'content': 'BK-1'}], 'shows': [{'id': self.base + '/rk/v1'}], 'subject_of': [{'subject_to': [{'classified_as': [{'id': 'https://creativecommons.org/publicdomain/zero/1.0/'}]}]}]},
            '/rk/v1': {'digitally_shown_by': [{'id': self.base + '/rk/d1'}]},
            '/rk/d1': {'access_point': [{'id': self.base + '/iiifr/full/max/0/default.jpg'}]},
        }
        self.write_shim()

    def write_shim(self, failures=(), cache_rename_failures=0):
        self.shim.write_text('''const realFetch = globalThis.fetch;
const fixtures = ''' + json.dumps(self.fixtures) + ''';
const failures = ''' + json.dumps(list(failures)) + ''';
globalThis.fetch = async (input, init) => {
  const u = new URL(input); const key = u.pathname === '/assets' ? u.pathname + u.search : u.pathname;
  if (failures.includes(key)) return new Response('failure', {status:503});
  if (key in fixtures) return new Response(JSON.stringify(fixtures[key]), {headers:{'Content-Type':'application/json'}});
  if (u.hostname === '127.0.0.1') { u.protocol = 'http:'; return realFetch(u, init); }
  throw new Error('Unexpected fixture request: ' + u.href);
};
''', encoding='utf-8')
        if cache_rename_failures:
            with self.shim.open('a', encoding='utf-8') as shim:
                shim.write('''
import cacheFs from 'node:fs/promises';
const realRename = cacheFs.rename;
let renameFailures = ''' + str(cache_rename_failures) + ''';
cacheFs.rename = async (source, target) => {
  if (String(target).endsWith('.curate-cache.json') && renameFailures !== 0) {
    if (renameFailures > 0) renameFailures--;
    throw Object.assign(new Error('EPERM: simulated Windows cache sharing violation'), {code:'EPERM'});
  }
  return realRename(source, target);
};
''')

    def cli_command(self, *args, fixture=False):
        cmd = [NODE]
        if fixture:
            cmd += ['--import', self.shim.as_uri()]
        return cmd + [str(SCRIPT), *args]

    def run_cli(self, *args, fixture=False, ok=True):
        result = subprocess.run(self.cli_command(*args, fixture=fixture), cwd=self.cwd, capture_output=True, text=True, timeout=40, encoding='utf-8')
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stderr + result.stdout)
        return result

    def test_help_and_actionable_argument_errors(self):
        self.assertIn('blueprint|map|plate|science|video', self.run_cli('--help').stdout)
        for args in [('search', 'wood', '--kind', 'unknown'), ('search', 'wood', '--limit', 'NaN'), ('search', 'wood', '--limt', '2'), ('fetch', 'V1', '--out', 'a.png', '--dir', 'assets'), ('search', 'wood', '--sheet=false'), ('unknown',), ('search', 'wood', '--resolution', '16k'), ('fetch', 'T1', '--maps', 'diffuse,all')]:
            with self.subTest(args=args):
                self.assertIn('node scripts/curate-media.mjs', self.run_cli(*args, ok=False).stderr)
        self.assertFalse((self.cwd / '.curate-cache.json').exists())

    def test_all_kinds_and_no_false_blueprints(self):
        for kind in ['texture', 'design', 'photo', 'blueprint', 'map', 'plate', 'science', 'video', 'all']:
            with self.subTest(kind=kind):
                result = json.loads(self.run_cli('search', 'wood', '--kind', kind, '--limit', '15', fixture=True).stdout)
                self.assertTrue(result['items'])
                self.assertEqual(result['errors'], [])
                if kind == 'all':
                    self.assertEqual({i['provider'] for i in result['items']}, {'polyhaven', 'vam', 'loc', 'wellcome', 'nasa', 'commons', 'met', 'aic', 'cleveland', 'japan', 'rijks'})
                if kind == 'blueprint':
                    self.assertTrue(all('/sheet/' in i['imageUrl'] for i in result['items']))
                    self.assertTrue(all('_150px' not in i['previewUrl'] for i in result['items']))

    def test_refs_survive_other_searches_and_texture_is_downloadable(self):
        a = json.loads(self.run_cli('search', 'wood', '--kind', 'texture', fixture=True).stdout)['items'][0]
        self.assertEqual(a['ref'], 'T1')
        self.assertEqual(a['imageUrl'], self.base + '/image')
        self.assertNotEqual(a['imageUrl'], a['previewUrl'])
        self.assertEqual(set(a['textureMaps']), {'diffuse', 'roughness', 'normal'})
        self.run_cli('search', 'wood', '--kind', 'design', fixture=True)
        b = json.loads(self.run_cli('search', 'wood', '--kind', 'texture', fixture=True).stdout)['items'][0]
        self.assertEqual(a['ref'], b['ref'])
        self.assertIn('V1', json.loads((self.cwd / '.curate-cache.json').read_text(encoding='utf-8'))['items'])

    @unittest.skipUnless(FFMPEG and FFPROBE, 'ffmpeg/ffprobe required for full decode')
    def test_batch_fetch_maps_integrity_sheet_credits_and_no_overwrite(self):
        self.run_cli('search', 'wood', '--kind', 'texture', fixture=True)
        self.run_cli('search', 'wood', '--kind', 'design', fixture=True)
        result = json.loads(self.run_cli('fetch', 'V1,T1', '--maps', 'all', '--dir', 'assets', '--sheet', fixture=True).stdout)
        self.assertEqual(result['count'], 4)
        self.assertTrue(all((i['width'], i['height'], i['integrity']) == (8, 6, 'full-decode') for i in result['files']))
        self.assertEqual(result['files'][0]['originalWidth'], 8)
        self.assertTrue((self.cwd / 'assets/sheet.html').exists())
        log = (self.cwd / 'assets/SOURCES.md').read_text(encoding='utf-8')
        self.assertIn('License:', log)
        self.assertIn('Powered by Poly Haven', log)
        self.assertIn('Victoria and Albert Museum', log)
        repeated = json.loads(self.run_cli('fetch', 'T1', '--dir', 'assets', fixture=True).stdout)
        self.assertTrue(repeated['files'][0]['saved'].endswith('-1.png'))
        self.assertFalse(list((self.cwd / 'assets').glob('*.part')))
        self.assertFalse(list(self.cwd.glob('*.lock')))

    def test_direct_url_partial_failure_and_limit(self):
        result = json.loads(self.run_cli('fetch', self.base + '/image', self.base + '/bad', '--dir', 'assets', ok=False).stdout)
        self.assertEqual(result['count'], 1)
        self.assertEqual(len(result['errors']), 1)
        self.assertIn('Rights not verified', (self.cwd / 'assets/SOURCES.md').read_text(encoding='utf-8'))
        result = json.loads(self.run_cli('fetch', self.base + '/large', '--max-mb', '1', ok=False).stdout)
        self.assertEqual(result['count'], 0)
        self.assertIn('max-mb', result['errors'][0]['message'])

    def test_explicit_file_and_missing_ref(self):
        self.run_cli('fetch', self.base + '/image', '--out', 'assets/sample.png')
        r = json.loads(self.run_cli('fetch', self.base + '/image', '--out', 'assets/sample.png', ok=False).stdout)
        self.assertIn('已存在', r['errors'][0]['message'])
        self.assertEqual((self.cwd / 'assets/sample.png').read_bytes(), self.image)
        self.run_cli('fetch', 'V999', ok=False)
        self.run_cli('fetch', 'file:///etc/passwd', ok=False)

    @unittest.skipUnless(FFMPEG and FFPROBE, 'ffmpeg/ffprobe required for corruption check')
    def test_corrupt_image_and_md5_rejected_before_delivery(self):
        result = json.loads(self.run_cli('fetch', self.base + '/corrupt', '--sheet', ok=False).stdout)
        self.assertEqual(result['count'], 0)
        self.fixtures['/files/wood']['Diffuse']['1k']['jpg'] = {'url': self.base + '/image', 'size': len(self.image), 'md5': '0' * 32}
        self.write_shim()
        self.run_cli('search', 'wood', '--kind', 'texture', fixture=True)
        result = json.loads(self.run_cli('fetch', 'T1', fixture=True, ok=False).stdout)
        self.assertIn('MD5', result['errors'][0]['message'])
        self.assertFalse(list((self.cwd / 'assets').glob('T1*')))

    def test_source_failure_distinct_from_zero_matches(self):
        self.write_shim(failures=['/v2/objects/search'])
        result = json.loads(self.run_cli('search', 'wood', '--kind', 'all', fixture=True).stdout)
        self.assertEqual(result['errors'][0]['source'], 'vam')
        self.write_shim(failures=['/catalogue/v2/images', '/w/api.php', '/api/item/search/jps-cross'])
        self.run_cli('search', 'wood', '--kind', 'plate', fixture=True, ok=False)
        self.fixtures['/catalogue/v2/images'] = {'results': []}
        self.fixtures['/w/api.php'] = {'query': {'pages': []}}
        self.fixtures['/api/item/search/jps-cross'] = {'hit': 0, 'list': []}
        self.write_shim()
        result = json.loads(self.run_cli('search', 'wood', '--kind', 'plate', fixture=True).stdout)
        self.assertEqual(result['count'], 0)
        self.assertEqual(result['errors'], [])

    def test_preview_escapes_text_and_reports_dimensions(self):
        self.fixtures['/v2/objects/search']['records'][0]['_primaryTitle'] = 'Wood <script>boom</script>'
        self.write_shim()
        self.run_cli('search', 'wood', '--kind', 'design', fixture=True)
        self.run_cli('preview', 'V1', '--sheet', '--dir', 'previews')
        html = (self.cwd / 'previews/candidates.html').read_text(encoding='utf-8')
        self.assertIn('&lt;script&gt;boom&lt;/script&gt;', html)
        self.assertIn('naturalWidth', html)
        self.assertIn('加载失败', html)

    @unittest.skipUnless(FFMPEG and FFPROBE, 'ffmpeg/ffprobe required for poster')
    def test_video_download_and_first_frame_poster(self):
        self.fixtures['/search']['collection']['items'][0]['data'][0]['media_type'] = 'video'
        self.fixtures['/manifest'] = [self.base + '/video~medium.mp4', self.base + '/video~orig.mov']
        self.write_shim()
        self.run_cli('search', 'earth', '--kind', 'video', fixture=True)
        result = json.loads(self.run_cli('fetch', 'N1', '--sheet', fixture=True).stdout)
        record = result['files'][0]
        self.assertTrue(record['poster'].endswith('-poster.jpg'))
        self.assertTrue(Path(record['poster']).is_file())
        self.assertEqual((record['width'], record['height']), (64, 48))
        self.assertEqual(record['integrity'], 'full-decode')
        self.assertIn('first-frame poster', (self.cwd / 'assets/SOURCES.md').read_text(encoding='utf-8'))

    @unittest.skipUnless(FFMPEG and FFPROBE, 'ffmpeg/ffprobe required for recovered video')
    def test_failed_video_rendition_falls_back_without_losing_reason(self):
        self.fixtures['/search']['collection']['items'][0]['data'][0]['media_type'] = 'video'
        self.fixtures['/manifest'] = [self.base + '/bad~medium.mp4', self.base + '/video~preview.mp4']
        self.write_shim()
        self.run_cli('search', 'earth', '--kind', 'video', fixture=True)
        data = json.loads(self.run_cli('fetch', 'N1', '--sheet', fixture=True).stdout)
        self.assertEqual(data['errors'], [])
        self.assertTrue(data['files'][0]['url'].endswith('~preview.mp4'))
        self.assertTrue(data['files'][0]['warnings'])
        self.assertTrue(Path(data['files'][0]['poster']).exists())

    def test_missing_tools_keep_download_and_report_unfinished_sheet(self):
        result = subprocess.run([NODE, str(SCRIPT), 'fetch', self.base + '/image', '--sheet'], cwd=self.cwd, env={**os.environ, 'PATH': ''}, capture_output=True, text=True, timeout=20, encoding='utf-8')
        self.assertEqual(result.returncode, 1)
        data = json.loads(result.stdout)
        self.assertEqual(data['count'], 1)
        self.assertTrue(Path(data['files'][0]['saved']).exists())
        self.assertEqual(data['files'][0]['integrity'], 'signature-and-length-only')
        self.assertIn('ffprobe', data['errors'][0]['message'])

    @staticmethod
    def cleanup_child(child):
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=10)

    def test_concurrent_searches_merge_cache_without_reassigning_refs(self):
        children = []
        for kind in ('texture', 'design', 'map', 'plate'):
            child = subprocess.Popen(self.cli_command('search', 'wood', '--kind', kind, fixture=True), cwd=self.cwd,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
            # LIFO cleanup runs before TemporaryDirectory cleanup, even on a failed
            # assertion, communicate timeout, or a later Popen failing to start.
            self.addCleanup(self.cleanup_child, child)
            children.append(child)
        for child in children:
            out, err = child.communicate(timeout=30)
            self.assertEqual(child.returncode, 0, out + err)
        items = json.loads((self.cwd / '.curate-cache.json').read_text(encoding='utf-8'))['items']
        self.assertEqual(set(items), {'T1', 'T2', 'V1', 'L1', 'W1', 'C1', 'M1', 'A1', 'K1', 'J1'})
        ids = [(i['provider'], i['sourceId']) for i in items.values()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_cache_replace_retries_busy_files_and_preserves_cache_on_failure(self):
        self.run_cli('search', 'wood', '--kind', 'design', fixture=True)
        self.write_shim(cache_rename_failures=2)
        result = json.loads(self.run_cli('search', 'wood', '--kind', 'texture', '--refresh', fixture=True).stdout)
        self.assertTrue(result['items'])
        cache = self.cwd / '.curate-cache.json'
        self.assertIn('V1', json.loads(cache.read_text(encoding='utf-8'))['items'])
        previous = cache.read_bytes()
        self.write_shim(cache_rename_failures=-1)
        failed = self.run_cli('search', 'wood', '--kind', 'texture', fixture=True, ok=False)
        self.assertIn('EPERM', failed.stderr)
        self.assertEqual(cache.read_bytes(), previous)
        self.assertFalse(list(self.cwd.glob('*.tmp')))
        self.assertFalse(list(self.cwd.glob('*.lock')))

    def test_map_selection_video_renditions_and_animation_filter(self):
        javascript = """import assert from 'node:assert/strict';
import {selectMap, selectNasaFile, interleave} from %s;
assert.equal(selectMap({nor_gl:{'2k':{jpg:{url:'gl'}}},nor_dx:{'1k':{jpg:{url:'dx'}}}},['nor_gl'],'1k').url,'gl');
assert.equal(selectMap({Diffuse:{'1k':{jpg:{url:'small'}},'8k':{jpg:{url:'large'}}}},['Diffuse'],'4k').url,'small');
assert.equal(selectNasaFile(['a~orig.mov','a~preview.mp4','a~medium.mp4'],'video'),'a~medium.mp4');
assert.equal(selectNasaFile(['a~thumb.jpg','a~orig.jpg'],'image'),'a~orig.jpg');
assert.equal(interleave([[{provider:'a',sourceId:'1'},{provider:'a',sourceId:'2'}],[{provider:'b',sourceId:'3'}]],2)[1].provider,'b');
""" % json.dumps(SCRIPT.as_uri())
        subprocess.run([NODE, '--input-type=module', '-e', javascript], check=True, capture_output=True, timeout=10)
        nasa = self.fixtures['/search']['collection']['items']
        nasa.insert(0, {'data': [{'nasa_id': 'animation', 'title': 'Launch Animation', 'media_type': 'video'}], 'links': [{'href': self.base + '/thumb', 'render': 'image'}]})
        self.write_shim()
        result = json.loads(self.run_cli('search', 'wood', '--kind', 'video', fixture=True).stdout)
        self.assertEqual([r['sourceId'] for r in result['items']], ['earth'])

    def test_relevance_rights_and_pixel_facts(self):
        javascript = '''import assert from 'node:assert/strict';
import {matchCount, rightsUse, describePixels} from %s;
assert.equal(matchCount('White Maple Veneer configuration figure', ['fig']), 0);
assert.equal(matchCount('Figs and leaves', ['fig']), 1);
assert.equal(matchCount('Plate 3, fig. 2: the heart', ['fig']), 0);
assert.equal(matchCount('Old maps of Ghent', ['ghent', 'map']), 2);
for (const [text, use] of [['CC BY-NC 4.0', 'reference'], ['V&A terms: permitted non-commercial uses only; commercial publication requires licensing', 'reference'], ['CC BY-ND 4.0', 'reference'], ['Public domain', 'page'], ['CC BY-SA 4.0', 'page'], ['CC0', 'page'], ['No known restrictions on publication.', 'page'], ['NASA media usage guidelines; generally not subject to US copyright; verify third-party credits', 'page'], ['Third-party rights mentioned; check item credits', 'check'], ['Rights not specified in search; check Rights & Access on item page', 'check'], ['GFDL', 'check']]) assert.equal(rightsUse(text), use, text);
const n = 48, half = Buffer.alloc(n * n * 3, 250);
for (let y = n / 2; y < n; y++) for (let x = 0; x < n; x++) half.fill((x + y) %% 2 ? 0 : 255, (y * n + x) * 3, (y * n + x) * 3 + 3);
const split = describePixels(half);
assert.ok(split.calm.includes('top') && !split.calm.includes('bottom'));
assert.equal(split.edgeFlat, false);
const paper = describePixels(Buffer.alloc(n * n * 3, 240));
assert.deepEqual([paper.paper, paper.tone, paper.mono, paper.edge, paper.calm.length], [true, 'light', true, '#f0f0f0', 5]);
''' % json.dumps(SCRIPT.as_uri())
        subprocess.run([NODE, '--input-type=module', '-e', javascript], check=True, capture_output=True, timeout=10)

    def test_off_subject_filtered_uses_sorted_and_queries_combined(self):
        self.fixtures['/photos/']['results'].append({'id': 'http://www.loc.gov/item/9/', 'title': 'America at work', 'image_url': [self.base + '/b.jpg']})
        self.write_shim()
        result = json.loads(self.run_cli('search', 'wood', '--kind', 'photo', fixture=True).stdout)
        self.assertEqual(result['filtered'], 1)
        self.assertNotIn('America at work', [i['title'] for i in result['items']])
        self.assertEqual([i['use'] for i in result['items']], sorted((i['use'] for i in result['items']), key=['page', 'check', 'reference'].index))
        design = json.loads(self.run_cli('search', 'wood | chair', '--kind', 'design', fixture=True).stdout)
        self.assertEqual(design['queries'], ['wood', 'chair'])
        self.assertEqual(design['items'][-1]['use'], 'reference')
        self.assertEqual(design['items'][-1]['provider'], 'vam')
        page = json.loads(self.run_cli('search', 'wood', '--kind', 'design', '--use', 'page', fixture=True).stdout)
        self.assertTrue(page['items'])
        self.assertTrue(all(i['use'] == 'page' for i in page['items']))
        self.run_cli('search', 'wood', '--use', 'free', ok=False)

    @unittest.skipUnless(FFMPEG and FFPROBE, 'ffmpeg/ffprobe required for contact PNG')
    def test_search_sheet_writes_readable_png_and_look(self):
        result = json.loads(self.run_cli('search', 'wood', '--kind', 'design', '--sheet', '--dir', 'cand', fixture=True).stdout)
        png_file = Path(result['sheetImage'])
        self.assertEqual(png_file.read_bytes()[:8], b'\x89PNG\r\n\x1a\n')
        self.assertTrue((self.cwd / 'cand/candidates.html').exists())
        look = result['items'][0]['look']
        self.assertEqual(set(look), {'tone', 'mono', 'edge', 'edgeFlat', 'paper', 'calm', 'ratio'})
        self.assertAlmostEqual(look['ratio'], 1.33, places=2)
        fetched = json.loads(self.run_cli('fetch', 'V1', '--dir', 'ref', '--sheet', fixture=True).stdout)
        self.assertEqual(fetched['files'][0]['use'], 'reference')
        self.assertTrue(any('生图参考' in w for w in fetched['files'][0]['warnings']))
        self.assertTrue(Path(fetched['sheetImage']).exists())
        self.assertIn('Use: reference only', (self.cwd / 'ref/SOURCES.md').read_text(encoding='utf-8'))

    def test_japan_and_rijks_records_and_colbase_fallback(self):
        design = json.loads(self.run_cli('search', 'wood', '--kind', 'design', '--limit', '10', fixture=True).stdout)['items']
        japan = next(i for i in design if i['provider'] == 'japan')
        self.assertEqual((japan['use'], japan['detail'].split(' · ')[0]), ('page', 'Wood box'))
        self.assertIn('/slideshow/', japan['imageUrl'])
        self.assertIn('ColBase', japan['attribution'])
        rijks = next(i for i in design if i['provider'] == 'rijks')
        self.assertEqual((rijks['title'], rijks['license'], rijks['use']), ('Wood chair', 'CC0', 'page'))
        self.assertTrue(rijks['imageUrl'].endswith('/iiifr/full/!2400,2400/0/default.jpg'))
        got = json.loads(self.run_cli('fetch', japan['ref'], fixture=True).stdout)['files'][0]
        self.assertIn('/slideshow_s/', got['url'])
        self.assertTrue(any('回退' in w for w in got['warnings']))
        cjk = json.loads(self.run_cli('search', '箱', '--kind', 'design', fixture=True).stdout)
        self.assertEqual(cjk['items'][0]['provider'], 'japan')
        self.assertGreater(cjk['count'], 1)


if __name__ == '__main__':
    unittest.main()
