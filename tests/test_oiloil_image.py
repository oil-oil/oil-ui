"""Run the oiloil CLI against a loopback server, with isolated fake credentials.

No real API calls, login state or credits are used. Filesystem faults happen after
the server has accepted a request, to exercise recovery of a charged response.
"""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/oiloil-image.mjs'
NODE = shutil.which('node')
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
ACCOUNT = 'https://ui.oiloil.org/account/?tab=images'
LOGIN = 'npx github:oil-oil/oil-cli login'


@unittest.skipUnless(NODE, 'Node is required')
class OiloilImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='oil-image-test-中文 #%-')
        self.addCleanup(self.temp.cleanup)
        self.cwd = Path(self.temp.name).resolve()
        self.env = dict(os.environ)
        for key in ('OIL_TOKEN', 'OIL_API', 'OIL_IMAGE_API', 'XDG_CONFIG_HOME', 'APPDATA', 'NODE_OPTIONS'):
            self.env.pop(key, None)
        self.env.update(OIL_TOKEN='fake-test-token', XDG_CONFIG_HOME=str(self.cwd / 'config'),
                        APPDATA=str(self.cwd / 'config'), TMPDIR=str(self.cwd),
                        TMP=str(self.cwd), TEMP=str(self.cwd), OIL_API='https://ui.oiloil.org')
        self.requests = []
        self.status = 200
        self.payload = {'image': {'mime_type': 'image/png', 'data': base64.b64encode(PNG).decode()},
                        'size': '1K', 'usage': {'credits': 7, 'balance': 93}}
        self.request_status = {'request_id': 'req-test', 'state': 'completed', 'credits': 7, 'run_id': None}
        self.raw = None
        self.disconnect = self.hang = self.redirect = False
        self.before_response = None
        self.release = threading.Event()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def serve(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                owner.requests.append({'path': self.path, 'method': self.command,
                                       'headers': dict(self.headers), 'body': json.loads(body) if body else None})
                if owner.disconnect:
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                if owner.hang:
                    owner.release.wait(5)
                    return
                if owner.before_response:
                    owner.before_response()
                default = (owner.request_status if self.command == 'GET' and self.path.startswith('/v1/requests/')
                           else {'skills': {'oil-ui-pro': {'latest': '99.0.0'}}} if self.path == '/gallery/api/store/versions'
                           else {'balance': 93} if self.command == 'GET' else owner.payload)
                data = (owner.raw if owner.raw is not None else json.dumps(default)).encode('utf-8')
                self.send_response(307 if owner.redirect else owner.status)
                if owner.redirect:
                    self.send_header('Location', owner.base + '/redirected')
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', len(data))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            do_POST = do_GET = serve

            def log_message(self, *_):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.env['OIL_IMAGE_API'] = self.base + '///'
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def call(self, *args, preload=None, script=SCRIPT):
        command = [NODE]
        if preload:
            command += ['--import', preload.as_uri()]
        result = subprocess.run([*command, str(script), *args], cwd=self.cwd, env=self.env,
                                capture_output=True, text=True, encoding='utf-8', timeout=15)
        for token in ('fake-test-token', 'config-test-token'):
            self.assertNotIn(token, result.stdout + result.stderr)
        self.assertNotIn('at async ', result.stderr)
        self.assertNotIn('file://', result.stderr)
        return result

    def evaluate(self, source):
        result = subprocess.run([NODE, '--input-type=module', '-e',
                                 f'import * as cli from {json.dumps(SCRIPT.as_uri())};\n' + source],
                                cwd=self.cwd, env=self.env, capture_output=True, text=True,
                                encoding='utf-8', timeout=15, check=True)
        return json.loads(result.stdout)

    def recovery_files(self):
        return list(self.cwd.glob('oiloil-image-*/response.json')) + list(self.cwd.glob('assets/oiloil-response-*.json'))

    def request_files(self):
        return list(self.cwd.glob('oiloil-image-*/request.json'))

    def assert_image(self, result, relative='assets/generated.png', data=PNG):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        file = self.cwd / relative
        self.assertEqual(file.read_bytes(), data)
        self.assertEqual(result.stdout, f'图片已保存到 {json.dumps(str(file), ensure_ascii=False)}；本次扣除 7 积分，剩余 93 积分。\n')

    def test_help_is_available_without_login_and_has_generic_examples(self):
        self.env.pop('OIL_TOKEN')
        for args in ((), ('--help',), ('image', '-h'), ('balance', '--help'), ('status', '--help')):
            result = self.call(*args)
            self.assertEqual(result.returncode, 0)
            for text in ('image', 'balance', 'status', '幂等键', '16 的倍数', '--ref', '2 MiB', '--名字=值',
                         'OIL_TOKEN', 'OIL_API', 'OIL_IMAGE_API', 'XDG_CONFIG_HOME', 'APPDATA', LOGIN, ACCOUNT, 'medium', '退出码'):
                self.assertIn(text, result.stdout)
            for text in ('单价', '费率', '加价', 'quality <', '--quality'):
                self.assertNotIn(text, result.stdout)
        self.assertEqual(self.requests, [])

    def test_generate_uses_exact_api_contract_and_fresh_uuid(self):
        self.assert_image(self.call('image', '<图片说明>'))
        second = self.call('image', '<图片说明>')
        self.assert_image(second, 'assets/generated-1.png')
        keys = []
        for request in self.requests:
            self.assertEqual((request['method'], request['path']), ('POST', '/v1/images'))
            self.assertEqual(request['body'], {'prompt': '<图片说明>', 'size': '1K'})
            self.assertEqual(request['headers']['Authorization'], 'Bearer fake-test-token')
            self.assertEqual(request['headers']['Content-Type'], 'application/json')
            key = request['headers']['Idempotency-Key']
            self.assertEqual(UUID(key).version, 4)
            keys.append(key)
        self.assertNotEqual(*keys)
        self.assertEqual(self.recovery_files(), [])
        self.assertEqual(self.request_files(), [])

    def test_background_is_passed_through_and_auto_uses_the_server_default(self):
        for value in ('transparent', '透明', 'opaque', 'auto'):
            with self.subTest(value=value):
                result = self.call('image', '<说明>', '--background', value)
                self.assertEqual(result.returncode, 0, result.stderr)
                body = self.requests[-1]['body']
                if value == 'auto':
                    self.assertNotIn('background', body)
                else:
                    self.assertEqual(body['background'], 'transparent' if value == '透明' else value)

    def test_balance_sends_get_without_body_or_idempotency_key(self):
        result = self.call('balance')
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, 'oiloil 余额：93 积分。\n', ''))
        request = self.requests[0]
        self.assertEqual((request['path'], request['method'], request['body']), ('/v1/credits', 'GET', None))
        self.assertNotIn('Idempotency-Key', request['headers'])
        self.assertEqual(self.recovery_files(), [])

    def test_status_queries_the_original_idempotency_key(self):
        key = '00000000-0000-4000-8000-000000000000'
        result = self.call('status', key)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, '原请求状态：completed；请求编号：req-test；已结算 7 积分。原图已过期或该请求早于结果恢复功能，无法通过 status 取回。\n', ''))
        request = self.requests[0]
        self.assertEqual((request['path'], request['method'], request['body']),
                         (f'/v1/requests/{key}?endpoint=images', 'GET', None))
        self.assertNotIn('Idempotency-Key', request['headers'])
        self.request_status.update(state='failed', credits=0)
        result = self.call('status', key)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('failed', result.stdout)
        self.assertIn('新的幂等键', result.stdout)

    def test_status_recovers_completed_image_after_disconnect(self):
        self.disconnect = True
        result = self.call('image', '<图片说明>', '--out', 'assets/lost.png')
        self.assertEqual(result.returncode, 6)
        self.assertIn('--out', result.stderr)
        key = self.requests[0]['headers']['Idempotency-Key']
        self.disconnect = False
        self.request_status.update(**self.payload)
        result = self.call('status', key)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('原图可恢复', result.stdout)
        self.assertFalse((self.cwd / 'assets/lost.png').exists())
        before = len(self.requests)
        self.assert_image(self.call('status', key, '--out', 'assets/lost.png'), 'assets/lost.png')
        self.assertTrue(all(request['method'] == 'GET' for request in self.requests[before:]))
        self.assertEqual(len([request for request in self.requests if request['method'] == 'POST']), 1)
        self.assertEqual(self.recovery_files(), [])
        files = self.request_files()
        self.assertEqual(len(files), 1)
        self.assertEqual(json.loads(files[0].read_text(encoding='utf-8'))['idempotency_key'], key)

    def test_completed_status_without_image_cannot_be_saved(self):
        key = '00000000-0000-4000-8000-000000000000'
        result = self.call('status', key)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('无法通过 status 取回', result.stdout)
        result = self.call('status', key, '--out', 'assets/generated.png')
        self.assertEqual(result.returncode, 7)
        self.assertIn('无法通过 status 取回', result.stderr)
        self.assertNotIn('生成响应保留', result.stderr)
        self.assertFalse((self.cwd / 'assets/generated.png').exists())
        self.assertEqual(self.recovery_files(), [])
        self.assertEqual(self.request_files(), [])

    def test_status_rejects_malformed_recoverable_response(self):
        self.request_status.update(image={'mime_type': 'image/avif', 'data': 'AAAA'},
                                   usage={'credits': 7, 'balance': 93})
        key = '00000000-0000-4000-8000-000000000000'
        result = self.call('status', key)
        self.assertEqual(result.returncode, 7)
        self.assertIn('图片格式或数据异常', result.stderr)
        self.assertFalse((self.cwd / 'assets/generated.png').exists())

    def test_gallery_and_image_api_environment_can_coexist(self):
        self.env['OIL_API'] = self.base + '/gallery'
        code = ("import importlib.util,json\n"
                f"spec=importlib.util.spec_from_file_location('check_update', {json.dumps(str(ROOT / 'scripts/check_update.py'))})\n"
                "module=importlib.util.module_from_spec(spec)\n"
                "spec.loader.exec_module(module)\n"
                "print(json.dumps(module.fetch('oil-ui-pro')))")
        result = subprocess.run([__import__('sys').executable, '-c', code], cwd=self.cwd, env=self.env,
                                capture_output=True, text=True, encoding='utf-8', timeout=15, check=True)
        self.assertEqual(json.loads(result.stdout), {'latest': '99.0.0', 'free': False})
        self.assertEqual(self.requests[-1]['path'], '/gallery/api/store/versions')
        self.call('balance')
        self.assertEqual(self.requests[-1]['path'], '/v1/credits')

    def test_status_rejects_positive_credits_before_completion(self):
        key = '00000000-0000-4000-8000-000000000000'
        for state in ('running', 'failed'):
            with self.subTest(state=state):
                self.request_status.update(state=state, credits=7)
                result = self.call('status', key)
                self.assertEqual(result.returncode, 7, result.stderr)
                self.assertEqual(result.stdout, '')
                self.assertIn('未返回有效的原请求状态', result.stderr)
                self.assertNotIn('新的幂等键', result.stderr)

    def test_cli_runs_through_a_linked_skill_directory(self):
        link = self.cwd / 'linked-skill'
        try:
            link.symlink_to(ROOT, target_is_directory=True)
        except OSError as error:
            self.skipTest(f'Symlinks unavailable: {error}')
        self.assert_image(self.call('image', '<说明>', script=link / 'scripts/oiloil-image.mjs'))
        self.env['NODE_OPTIONS'] = '--preserve-symlinks-main'
        self.assert_image(self.call('image', '<说明>', script=link / 'scripts/oiloil-image.mjs'), 'assets/generated-1.png')

    def test_argument_forms_and_size_normalization(self):
        cases = [(['--size=2k', 'image', '-p', '<说明>', '-o=result.png'], '2K', '<说明>'),
                 (['image', '<第一段>', '<第二段>', '--size', '1024 X 1536'], '1024x1536', '<第一段> <第二段>'),
                 (['-s', '1024×1536', 'image', '--', '-<说明>'], '1024x1536', '-<说明>'),
                 (['image', '--', '--help'], '1K', '--help'),
                 (['image', '--prompt=<说明>', '--size=4k'], '4K', '<说明>'),
                 (['image', '<说明>', '--size=1024x640'], '1024x640', '<说明>'),
                 (['image', '<说明>', '--size=3840x2160'], '3840x2160', '<说明>')]
        for args, size, prompt in cases:
            with self.subTest(args=args):
                result = self.call(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.requests[-1]['body'], {'prompt': prompt, 'size': size})

    def test_reference_accepts_supported_content_at_limit_regardless_of_suffix(self):
        for index, (mime, data) in enumerate((('image/png', PNG), ('image/jpeg', b'\xff\xd8\xff\xe0test'),
                                             ('image/webp', b'RIFF\x04\x00\x00\x00WEBPtest'))):
            with self.subTest(mime=mime):
                file = self.cwd / f'ref-{index}.bin'
                if index == 0:
                    data += b'\0' * (2 * 1024 * 1024 - len(data))
                file.write_bytes(data)
                result = self.call('image', '<修改说明>', '--ref', str(file))
                self.assertEqual(result.returncode, 0, result.stderr)
                body = self.requests[-1]['body']
                self.assertEqual(set(body), {'prompt', 'size', 'reference_image'})
                self.assertEqual(body['reference_image'], f'data:{mime};base64,{base64.b64encode(data).decode()}')

    def test_invalid_reference_and_local_output_fail_before_request(self):
        (self.cwd / 'large.png').write_bytes(PNG + b'\0' * (2 * 1024 * 1024))
        (self.cwd / 'invalid.png').write_bytes(b'<not an image>')
        (self.cwd / 'blocked').write_text('file', encoding='utf-8')
        for args, code in ((['--ref', 'large.png'], 2), (['--ref', 'invalid.png'], 2),
                           (['--ref', 'missing.png'], 1), (['--ref', '.'], 2),
                           (['--out', 'blocked/file.png'], 1), (['--out', str(self.cwd)], 2)):
            with self.subTest(args=args):
                result = self.call('image', '<说明>', *args)
                self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(self.requests, [])

    def test_bad_arguments_never_send_a_request(self):
        valid_key = '00000000-0000-4000-8000-000000000000'
        for args in (['unknown'], ['image'], ['--size', '1K'], ['image', '<说明>', '--size=auto'],
                     ['image', '<说明>', '--size=0x1024'], ['image', '--out'],
                     ['image', '<说明>', '--size=1000x1000'], ['image', '<说明>', '--size=512x512'],
                     ['image', '<说明>', '--size=1024x1023'], ['image', '<说明>', '--size=4096x1024'],
                     ['image', '<说明>', '--size=3840x1024'], ['image', '<说明>', '--size=800x800'],
                     ['image', '<说明>', '--size=3840x2176'],
                     ['image', '<说明>', '--ref=a', '--ref=b'], ['image', '<说明>', '--quality=medium'],
                     ['image', '--prompt=a', 'b'], ['image', 'a', '--out=assets/'],
                     ['balance', '--ref=a'], ['balance', '--timeout=0'], ['balance', '--timeout=NaN'],
                     ['status'], ['status', 'not-a-key'], ['status', valid_key, 'extra'],
                     ['status', valid_key, '--ref=a']):
            with self.subTest(args=args):
                result = self.call(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('--help', result.stderr)
        self.assertEqual(self.requests, [])

    def test_output_format_wins_and_existing_results_survive(self):
        assets = self.cwd / 'assets'
        assets.mkdir()
        (assets / 'result.png').write_bytes(b'existing png')
        (assets / 'result.webp').write_bytes(b'existing webp')
        self.payload['image']['mime_type'] = 'image/webp'
        self.assert_image(self.call('image', '<说明>', '--out=assets/result.png'), 'assets/result-1.webp')
        self.assertEqual((assets / 'result.png').read_bytes(), b'existing png')
        self.assertEqual((assets / 'result.webp').read_bytes(), b'existing webp')
        self.assert_image(self.call('image', '<说明>', '--out=assets/no-extension'), 'assets/no-extension.webp')

    def test_large_generated_response_does_not_overflow_base64_validation(self):
        data = PNG + b'\0' * (8 * 1024 * 1024)
        self.payload['image']['data'] = base64.b64encode(data).decode()
        self.assert_image(self.call('image', '<说明>', '--size=4K'), data=data)
        self.assertEqual(self.recovery_files(), [])

    def test_jpeg_alias_and_case_are_preserved_when_the_format_matches(self):
        self.payload['image']['mime_type'] = 'image/jpeg'
        self.assert_image(self.call('image', '<说明>', '-o', 'assets/result.JPEG'), 'assets/result.JPEG')
        self.assert_image(self.call('image', '<说明>', '-o', 'assets/result.png'), 'assets/result.jpg')

    def test_environment_token_takes_priority_and_config_api_is_ignored(self):
        config = self.cwd / 'config/oil/config.json'
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({'token': ' config-test-token ', 'api': 'http://invalid.example'}), encoding='utf-8')
        self.assertEqual(self.call('balance').returncode, 0)
        self.assertEqual(self.requests[-1]['headers']['Authorization'], 'Bearer fake-test-token')
        self.env['OIL_TOKEN'] = '  '
        for args in (('balance',), ('image', '<说明>')):
            self.assertEqual(self.call(*args).returncode, 0)
            self.assertEqual(self.requests[-1]['headers']['Authorization'], 'Bearer config-test-token')

    def test_config_locations_for_xdg_default_and_windows(self):
        cases = [[{}, 'linux', '/test-user'], [{'XDG_CONFIG_HOME': '/xdg'}, 'darwin', '/test-user'],
                 [{'APPDATA': 'C:\\roaming', 'XDG_CONFIG_HOME': 'C:\\ignored'}, 'win32', 'C:\\user'],
                 [{}, 'win32', 'C:\\user']]
        result = self.evaluate(f'console.log(JSON.stringify({json.dumps(cases)}.map(args => cli.tokenConfigPath(...args))));')
        self.assertEqual(result, ['/test-user/.config/oil/config.json', '/xdg/oil/config.json',
                                  'C:\\roaming\\oil\\config.json', 'C:\\user\\AppData\\Roaming\\oil\\config.json'])
        config = self.cwd / 'test-user/.config/oil/config.json'
        config.parent.mkdir(parents=True)
        config.write_text('{"token":"config-test-token"}', encoding='utf-8')
        # Read an explicit fake home; never inspect the user's real CLI config.
        self.assertTrue(self.evaluate(f'console.log(JSON.stringify((await cli.readOilToken({{}}, "linux", {json.dumps(str(config.parents[2]))})) === "config-test-token"));'))

    def test_skill_guides_login_before_generation(self):
        text = (ROOT / 'references/media.md').read_text(encoding='utf-8')
        self.assertIn('oiloil-image.mjs balance', text)
        self.assertIn(LOGIN, text)
        self.assertIn(ACCOUNT, text)
        self.assertIn('浏览器授权完成后继续当前任务', text)
        self.assertIn('只提示一次', text)

    def test_missing_empty_or_malformed_config_explains_login_without_requests(self):
        self.env.pop('OIL_TOKEN')
        config = self.cwd / 'config/oil/config.json'
        config.parent.mkdir(parents=True)
        for raw in (None, '{', 'null', '[]', '{}', '{"token":42}', '{"token":"  "}'):
            with self.subTest(raw=raw):
                if raw is not None:
                    config.write_text(raw, encoding='utf-8')
                for command in ('balance', 'image'):
                    result = self.call(command, *(['<说明>'] if command == 'image' else []))
                    self.assertEqual(result.returncode, 3)
                    self.assertIn('尚未登录 oiloil', result.stderr)
                    self.assertIn(LOGIN, result.stderr)
                    self.assertIn(ACCOUNT, result.stderr)
                    self.assertEqual(len(result.stderr.splitlines()), 1)
        self.assertEqual(self.requests, [])

    def test_auth_and_balance_errors_have_distinct_codes_and_no_upstream_text(self):
        for status, code, text in ((401, 5, '登录状态已失效'), (402, 4, '余额不足')):
            with self.subTest(status=status):
                self.status = status
                self.raw = '<upstream private text>'
                result = self.call('image', '<说明>')
                self.assertEqual(result.returncode, code)
                self.assertEqual(result.stdout, '')
                self.assertIn(text, result.stderr)
                self.assertIn(ACCOUNT, result.stderr)
                self.assertNotIn('upstream', result.stderr)
                self.assertEqual(len(result.stderr.splitlines()), 1)
                if status == 401:
                    self.assertIn(LOGIN, result.stderr)
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(self.recovery_files(), [])

    def test_recovery_command_quotes_literal_paths_for_the_shell(self):
        quoted = self.evaluate("""console.log(JSON.stringify({
          posix: cli.shellQuote("a$b'c", "linux"),
          powershell: cli.shellQuote("a$b'c", "win32")
        }));""")
        self.assertEqual(quoted['posix'], "'a$b'\\''c'")
        self.assertEqual(quoted['powershell'], "'a$b''c'")
        self.disconnect = True
        result = self.call('image', '<说明>', '--out', 'assets/$literal.webp')
        self.assertEqual(result.returncode, 6)
        self.assertIn(f"--out '{self.cwd.as_posix()}/assets/$literal.webp'", result.stderr)

    def test_transport_failure_preserves_the_key_for_status_without_retrying(self):
        self.disconnect = True
        result = self.call('image', '<说明>')
        self.assertEqual(result.returncode, 6)
        self.assertIn('无法确认本次是否扣费', result.stderr)
        self.assertIn(ACCOUNT, result.stderr)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.recovery_files(), [])
        key = self.requests[0]['headers']['Idempotency-Key']
        self.assertIn(f'status {key}', result.stderr)
        files = self.request_files()
        self.assertEqual(len(files), 1)
        metadata = json.loads(files[0].read_text(encoding='utf-8'))
        self.assertEqual(metadata, {'endpoint': 'images', 'idempotency_key': key})
        self.assertNotIn('<说明>', files[0].read_text(encoding='utf-8'))

        self.disconnect = False
        self.request_status.update(state='running', credits=0)
        status = self.call('status', key)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn('running', status.stdout)
        self.assertIn('请勿重新生成', status.stdout)

        self.disconnect = True
        result = self.call('balance')
        self.assertEqual(result.returncode, 6)
        self.assertIn('暂时无法查询余额', result.stderr)

    def test_timeout_aborts_once(self):
        self.hang = True
        result = self.call('image', '<说明>', '--timeout=100')
        self.release.set()
        self.assertEqual(result.returncode, 6)
        self.assertIn('请求超时', result.stderr)
        self.assertEqual(len(self.requests), 1)

    def test_redirects_do_not_forward_token_or_resubmit(self):
        self.redirect = True
        result = self.call('image', '<说明>')
        self.assertEqual(result.returncode, 6)
        self.assertEqual(len(self.requests), 1)

    def test_definite_http_failures_do_not_create_paid_response_recovery(self):
        self.status = 400
        self.raw = json.dumps({'error': {'message': 'size 超出上游支持范围'}})
        result = self.call('image', '<说明>')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('size 超出上游支持范围', result.stderr)
        self.assertNotIn('不要重新生图', result.stderr)
        self.assertEqual(self.recovery_files(), [])
        self.assertEqual(self.request_files(), [])

        self.status = 429
        result = self.call('image', '<说明>')
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertIn('HTTP 429', result.stderr)
        self.assertNotIn('不要重新生图', result.stderr)
        self.assertEqual(self.recovery_files(), [])
        self.assertEqual(self.request_files(), [])

    def test_idempotency_conflict_retains_the_key_but_not_an_error_response(self):
        self.status = 409
        self.raw = json.dumps({'error': {'message': 'request_in_progress'}})
        result = self.call('image', '<说明>')
        self.assertEqual(result.returncode, 7, result.stderr)
        key = self.requests[0]['headers']['Idempotency-Key']
        self.assertIn(f'status {key}', result.stderr)
        self.assertEqual(self.recovery_files(), [])
        self.assertEqual(len(self.request_files()), 1)

    def test_bad_api_address_is_rejected_before_request(self):
        for address in ('file:///tmp/test', 'http://user:secret@localhost', self.base + '?token=secret', 'invalid'):
            self.env['OIL_IMAGE_API'] = address
            result = self.call('balance')
            self.assertEqual(result.returncode, 2)
            self.assertNotIn('secret', result.stderr)
        self.assertEqual(self.requests, [])

    def test_post_response_output_failure_saves_to_recovery_directory(self):
        def block_output():
            (self.cwd / 'assets').rmdir()
            (self.cwd / 'assets').write_text('blocked after request', encoding='utf-8')
        self.before_response = block_output
        result = self.call('image', '<说明>')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertIn('原输出位置写入失败，已保存到备用目录', result.stdout)
        actual = json.loads(result.stdout.split('图片已保存到 ', 1)[1].split('；', 1)[0])
        self.assertEqual(Path(actual).read_bytes(), PNG)
        files = self.recovery_files()
        self.assertEqual(len(files), 1)
        self.assertEqual(json.loads(files[0].read_text(encoding='utf-8')), self.payload)

    def test_missing_usage_does_not_discard_the_image_or_response(self):
        self.payload.pop('usage')
        result = self.call('image', '<说明>')
        self.assertEqual(result.returncode, 7)
        self.assertEqual((self.cwd / 'assets/generated.png').read_bytes(), PNG)
        self.assertIn('图片已保存到', result.stderr)
        self.assertIn('不要重新生图', result.stderr)
        self.assertEqual(json.loads(self.recovery_files()[0].read_text(encoding='utf-8')), self.payload)

    def test_invalid_paid_response_is_preserved_verbatim(self):
        for raw in ('<malformed response>', json.dumps({'image': {'mime_type': 'image/avif', 'data': 'AAAA'}}),
                    json.dumps({'image': {'mime_type': 'constructor', 'data': 'AAAA'}}),
                    json.dumps({'image': {'mime_type': 'image/png', 'data': '!bad!'}})):
            with self.subTest(raw=raw):
                self.raw = raw
                previous = set(self.recovery_files())
                result = self.call('image', '<说明>')
                self.assertEqual(result.returncode, 7)
                files = set(self.recovery_files()) - previous
                self.assertEqual(len(files), 1)
                file = files.pop()
                self.assertEqual(file.read_text(encoding='utf-8'), raw)
                self.assertIn(json.dumps(str(file), ensure_ascii=False), result.stderr)
                self.assertIn('不要重新生图', result.stderr)

    def test_both_image_writes_failing_leave_the_received_response(self):
        shim = self.cwd / 'fail-image-writes.mjs'
        shim.write_text('''import fs from 'node:fs/promises';
const realOpen = fs.open;
fs.open = async (file, ...args) => {
  if (String(file).endsWith('.png')) throw Object.assign(new Error('fixture'), {code: 'ENOSPC'});
  return realOpen(file, ...args);
};''', encoding='utf-8')
        result = self.call('image', '<说明>', preload=shim)
        self.assertEqual(result.returncode, 8)
        files = self.recovery_files()
        self.assertEqual(len(files), 1)
        self.assertEqual(json.loads(files[0].read_text(encoding='utf-8')), self.payload)
        self.assertIn(json.dumps(str(files[0]), ensure_ascii=False), result.stderr)
        self.assertNotIn('fixture', result.stderr)
        self.assertEqual(len(self.requests), 1)

    def test_response_write_failure_uses_a_second_location(self):
        shim = self.cwd / 'fail-response-write.mjs'
        shim.write_text('''import fs from 'node:fs/promises';
const realOpen = fs.open;
fs.open = async (file, ...args) => {
  const handle = await realOpen(file, ...args);
  if (String(file).endsWith('response.json')) handle.writeFile = async () => { throw new Error('fixture'); };
  return handle;
};''', encoding='utf-8')
        self.raw = '<malformed response to preserve>'
        result = self.call('image', '<说明>', preload=shim)
        self.assertEqual(result.returncode, 7)
        backups = list(self.cwd.glob('assets/oiloil-response-*.json'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding='utf-8'), self.raw)
        self.assertIn(json.dumps(str(backups[0]), ensure_ascii=False), result.stderr)

    def test_server_error_is_not_retried_and_received_data_is_retained(self):
        self.status = 503
        self.raw = '<provider detail>'
        result = self.call('image', '<说明>')
        self.assertEqual(result.returncode, 7)
        self.assertIn('HTTP 503', result.stderr)
        self.assertNotIn('provider detail', result.stderr)
        self.assertEqual(self.recovery_files()[0].read_text(encoding='utf-8'), self.raw)
        self.assertEqual(len(self.requests), 1)

    def test_invalid_balance_is_not_reported_as_success(self):
        for raw in ('{}', '{"balance":"93"}', '{"balance":-1}', 'null', '<invalid>'):
            self.raw = raw
            result = self.call('balance')
            self.assertEqual(result.returncode, 7)
            self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
