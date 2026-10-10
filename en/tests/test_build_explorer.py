"""Observable builder contracts. Run with Python's unittest discovery."""

import base64
from contextlib import redirect_stderr
import importlib.util
from html.parser import HTMLParser
import io
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_explorer", ROOT / "scripts" / "build_explorer.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class ExplorerBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.manifest = self.folder / "manifest.json"
        self.output = self.folder / "output" / "explore.html"
        self.source = self.folder / "sample.html"
        self.source.write_text('<!doctype html><html><head><style>body{color:#123}</style></head><body>Same content<script>window.bad=true</script></body></html>', encoding="utf-8")
        self.data = {"schemaVersion": 1, "project": "Project", "brief": "Compare the same content", "round": "01", "candidates": [{"id": "a", "name": "Direction one", "concept": "Editorial", "typography": "Serif and sans", "palette": ["#112233", "#fff"], "traits": ["Large headings"], "kind": "html", "source": "sample.html"}]}
        self.save()

    def save(self):
        self.manifest.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

    def payload(self, page):
        return json.loads(page.split("const DATA = ", 1)[1].split(";\n", 1)[0])

    def test_lang_is_optional_and_preserved_when_explicit(self):
        builder.build(self.manifest, self.output)
        self.assertNotIn("lang", self.payload(self.output.read_text(encoding="utf-8")))
        for lang in ("zh", "en"):
            with self.subTest(lang=lang):
                self.data["lang"] = lang
                self.save()
                builder.build(self.manifest, self.output, force=True)
                self.assertEqual(self.payload(self.output.read_text(encoding="utf-8"))["lang"], lang)

    def test_invalid_lang_preserves_existing_output(self):
        builder.build(self.manifest, self.output)
        original = self.output.read_bytes()
        for lang in (None, "", "ZH", "zh-CN", "en-US", "fr", 1, True, [], {}):
            with self.subTest(lang=lang):
                self.data["lang"] = lang
                self.save()
                with self.assertRaisesRegex(ValueError, "manifest.lang"):
                    builder.build(self.manifest, self.output, force=True)
                self.assertEqual(original, self.output.read_bytes())

    def test_interface_strings_are_complete_and_centralized(self):
        template = builder.TEMPLATE.read_text(encoding="utf-8")
        table_text = template.split("const I18N = ", 1)[1].split(";\n", 1)[0]
        table = json.loads(table_text)
        self.assertEqual(set(table), {"zh", "en"})
        self.assertEqual(set(table["zh"]), set(table["en"]))
        keys = set(re.findall(r"\bt\('([^']+)'", template))
        keys.update(re.findall(r'data-i18n(?:-[\w-]+)?="([^"]+)"', template))
        self.assertEqual(keys, set(table["zh"]))
        for key in keys:
            self.assertTrue(table["zh"][key], key)
            self.assertTrue(table["en"][key], key)
            self.assertNotRegex(table["en"][key], r"[\u3400-\u9fff]", key)
            placeholders = lambda value: set(re.findall(r"\{(\w+)\}", value))
            self.assertEqual(placeholders(table["zh"][key]), placeholders(table["en"][key]), key)
        # Both locales are shipped for browser detection; neither may leak into
        # markup or JavaScript outside this single table (comments are not UI).
        shell = template.replace(table_text, "{}")
        shell = re.sub(r"/\*.*?\*/|(?m:^\s*//[^\n]*)", "", shell, flags=re.S)
        self.assertNotRegex(shell, r"[\u3400-\u9fff]")

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed to execute the page's language and copy functions")
    def test_browser_language_fallback_and_copied_sentence(self):
        template = builder.TEMPLATE.read_text(encoding="utf-8")
        translations = template.split("// Interface strings:", 1)[1].split("(()=>{", 1)[0]
        translations = translations[translations.index("const I18N = "):]
        copy_function = template.split(" function copyText()", 1)[1].split("\n async function copy", 1)[0]
        number_function = template.split("no=c=>", 1)[1].split(",vtName=", 1)[0]
        cases = [(None, "zh-CN", "zh"), (None, "ZH-hant", "zh"),
                 (None, "en-US", "en"), (None, "fr-FR", "en"),
                 (None, "", "en"), ("zh", "en-US", "zh"), ("en", "zh-CN", "en")]
        program = "const results=[];\n"
        for lang, browser_lang, expected in cases:
            for round_value, notes, baseline in (("01", "  More space  ", False), ("", "", False), ("02", "", True)):
                data = {"round": round_value}
                if lang is not None:
                    data["lang"] = lang
                program += "{\nconst DATA=" + json.dumps(data) + ";const navigator={language:" + json.dumps(browser_lang) + "};\n"
                program += translations
                program += "const c={name:'Direction A',baseline:" + json.dumps(baseline) + "};const DIRS=[c],byId={a:c},st={chosen:'a',notes:" + json.dumps(notes) + "};\n"
                program += "const no=c=>" + number_function + ";\nfunction copyText()" + copy_function
                program += "\nresults.push({lang:LANG,text:copyText()});\n}\n"
        program += "console.log(JSON.stringify(results));"
        run = subprocess.run([shutil.which("node"), "-e", program], capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        results = iter(json.loads(run.stdout))
        for _, _, expected in cases:
            # Chinese strings below are the zh locale's own UI output and must stay Chinese.
            number = "现状" if expected == "zh" else "Current"
            texts = (["01：选 01 Direction A", "选 01 Direction A", f"02：选 {number} Direction A"]
                     if expected == "zh" else ["Round 01: Go with 01 Direction A", "Go with 01 Direction A", f"Round 02: Go with {number} Direction A"])
            for text in texts:
                self.assertEqual(next(results), {"lang": expected, "text": text})

    @unittest.skipUnless(shutil.which("node") and (shutil.which("google-chrome") or shutil.which("chromium") or
                         Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome").is_file()),
                         "Chrome/Chromium is needed for rendered interface checks")
    def test_rendered_interfaces_do_not_mix_languages(self):
        chrome = (shutil.which("google-chrome") or shutil.which("chromium") or
                  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        self.source.write_text('<html><head></head><body>Sample</body></html>', encoding="utf-8")
        self.data.update(project="Demo", brief="Compare directions", round="01")
        self.data["candidates"][0].update(name="Direction A", concept="Clear hierarchy", typography="System font", traits=["Large headings"])
        self.data["candidates"].append(dict(self.data["candidates"][0], id="b", baseline=True, interactive=True))
        probe = r"""<script>
(async()=>{
 const snapshots=[],copied=[];
 Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>copied.push(text)},configurable:true});
 const capture=()=>{
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  let n;while(n=walker.nextNode())if(!n.parentElement.closest('script,style'))snapshots.push(n.textContent.trim());
  document.querySelectorAll('[aria-label],[title],[placeholder]').forEach(n=>['aria-label','title','placeholder'].forEach(a=>{if(n.hasAttribute(a))snapshots.push(n.getAttribute(a));}));
 };
 const initial={loupe:!document.querySelector('#loupe').hidden,current:document.querySelector('.slide.is-current').dataset.id,mobile:document.querySelector('[data-viewport=mobile]').getAttribute('aria-pressed'),cards:document.querySelectorAll('.card').length,descriptions:[...document.querySelectorAll('.lede')].every(n=>getComputedStyle(n).display!=='none')};
 capture();document.querySelector('[data-layout=loupe]').click();capture();
 document.querySelector('#zoom').click();capture();document.querySelector('#zoom').click();
 document.querySelector('#info-body [data-pick]').click();await Promise.resolve();capture();
 navigator.clipboard.writeText=async()=>{throw Error('denied')};document.execCommand=()=>false;
 document.querySelector('#info-body [data-pick]').click();await Promise.resolve();await Promise.resolve();capture();
 const result=document.createElement('pre');result.id='i18n-result';result.textContent=JSON.stringify({lang:document.documentElement.lang,title:document.title,snapshots,copied,initial,saved:JSON.parse(localStorage.getItem(`oil-ui:${DATA.fingerprint}`))});document.body.append(result);
})();
</script>"""
        table = json.loads(builder.TEMPLATE.read_text(encoding="utf-8").split("const I18N = ", 1)[1].split(";\n", 1)[0])
        for lang in ("zh", "en"):
            with self.subTest(lang=lang):
                self.data["lang"] = lang
                self.save()
                builder.build(self.manifest, self.output, force=True)
                page = self.output.read_text(encoding="utf-8")
                key = "oil-ui:" + self.payload(page)["fingerprint"]
                legacy = {"layout": "loupe", "viewport": "mobile", "current": "b", "chosen": "a",
                          "visible": [], "notesOn": False, "notes": "Old private note"}
                seed = "<script>localStorage.setItem(" + json.dumps(key) + "," + json.dumps(json.dumps(legacy)) + ");</script>"
                page = page.replace("<script>\nconst DATA", seed + "<script>\nconst DATA", 1)
                page = page.replace("</body></html>", probe + "</body></html>")
                self.output.write_text(page, encoding="utf-8")
                # Use the debugging pipe rather than virtual time: previews can
                # keep animation frames alive, so --dump-dom may never finish.
                runner = r"""
import {spawn} from 'node:child_process';
const chrome=spawn(process.argv[1],['--headless=new','--remote-debugging-pipe',
 '--no-first-run','--no-default-browser-check','--disable-extensions',
 '--force-prefers-reduced-motion',`--user-data-dir=${process.argv[2]}`,'about:blank'],
 {stdio:['ignore','ignore','ignore','pipe','pipe']});
let seq=0,buffer='';const pending=new Map();
chrome.on('error',error=>{console.error(error);process.exitCode=1;});
chrome.stdio[4].on('data',data=>{
 buffer+=data.toString();let end;
 while((end=buffer.indexOf('\0'))>=0){
  const message=JSON.parse(buffer.slice(0,end));buffer=buffer.slice(end+1);
  if(pending.has(message.id)){const {resolve,reject}=pending.get(message.id);pending.delete(message.id);
   message.error?reject(Error(message.error.message)):resolve(message.result);}
 }
});
const send=(method,params={},sessionId)=>new Promise((resolve,reject)=>{
 const id=++seq;pending.set(id,{resolve,reject});
 chrome.stdio[3].write(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})})+'\0');
});
const deadline=setTimeout(()=>{console.error('Browser probe timed out');chrome.kill('SIGKILL');process.exitCode=1;},15000);
try{
 const {targetId}=await send('Target.createTarget',{url:'about:blank'});
 const {sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});
 await send('Page.enable',{},sessionId);
 await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]},sessionId);
 await send('Page.navigate',{url:process.argv[3]},sessionId);
 let result;
 for(let i=0;i<100;i++){
  const response=await send('Runtime.evaluate',{expression:"document.querySelector('#i18n-result')?.textContent",returnByValue:true},sessionId);
  result=response.result.value;if(result)break;
  await new Promise(resolve=>setTimeout(resolve,50));
 }
 if(!result)throw Error('The page did not complete its interface/copy probe');
 console.log(result);
}catch(error){console.error(error);process.exitCode=1;}
finally{clearTimeout(deadline);chrome.kill();}
"""
                run = subprocess.run([shutil.which("node"), "--input-type=module", "-e", runner, chrome,
                                      str(self.folder / ("chrome-" + lang)), self.output.as_uri()],
                                     capture_output=True, text=True, timeout=25)
                self.assertEqual(run.returncode, 0, run.stderr)
                observed = json.loads(run.stdout)
                self.assertEqual(observed["lang"], table[lang]["htmlLang"])
                self.assertEqual(observed["title"], table[lang]["projectTitle"].replace("{project}", "Demo").replace("{edition}", " Pro" if builder.SKILL_ROOT.name == "oil-ui-pro" else ""))
                self.assertEqual(observed["initial"], {"loupe": True, "current": "b", "mobile": "true", "cards": 2, "descriptions": True})
                self.assertEqual(set(observed["saved"]), {"layout", "viewport", "current", "chosen"})
                self.assertEqual(observed["saved"]["chosen"], "b")
                strings = observed["snapshots"]
                self.assertNotIn("Old private note", strings)
                for key in ("compare", "loupe", "layoutLabel", "viewportLabel",
                            "baseline", "fonts", "traits", "actual", "fit", "empty", "copied", "copyFailed"):
                    self.assertIn(table[lang][key], strings, key)
                    other = table["en" if lang == "zh" else "zh"][key]
                    self.assertNotIn(other, strings, key)
                if lang == "en":
                    self.assertNotRegex("\n".join(strings), r"[\u3400-\u9fff]")
                # The zh branch checks the Chinese locale's copied sentence verbatim.
                self.assertEqual(observed["copied"], ["01：选 现状 Direction A"] if lang == "zh"
                                 else ["Round 01: Go with Current Direction A"])

    def test_portable_single_file_and_html_payload(self):
        result = builder.build(self.manifest, self.output)
        page = self.output.read_text(encoding="utf-8")
        self.assertEqual(result["candidates"], 1)
        self.assertIn("Same content", page)
        self.assertNotIn(str(self.folder), page)
        self.assertNotIn(builder.MARKER, page)
        self.assertIn("script-src 'none'", page)

    def test_metadata_cannot_close_script(self):
        self.data["project"] = '</script><script>window.injected=true</script>'
        self.save()
        builder.build(self.manifest, self.output)
        page = self.output.read_text(encoding="utf-8")
        self.assertNotIn(self.data["project"], page)
        self.assertIn('\\u003c/script>', page)

    def test_csp_is_inserted_in_actual_head_not_a_comment(self):
        self.source.write_text('''<!doctype html>
        <!-- Skeleton: <head> \u2028 extra text -->
        <html><head data-note="a > b"></head><body>content</body></html>''', encoding="utf-8")
        content = builder.prepare_html(self.source)
        observed = []
        class Tags(HTMLParser):
            def handle_starttag(self, tag, attrs):
                observed.append((tag, dict(attrs)))
        Tags().feed(content)
        meta = [attrs for tag, attrs in observed if tag == "meta"]
        self.assertEqual(meta, [{"http-equiv": "Content-Security-Policy", "content": builder.PREVIEW_CSP}])
        self.assertEqual([tag for tag, attrs in observed][:3], ["html", "head", "meta"])

    def test_nested_documents_are_rejected_before_replacing_output(self):
        builder.build(self.manifest, self.output)
        original = self.output.read_bytes()
        self.source.write_text('''<html><head></head><body>
        <iframe srcdoc="&lt;img src='https://example.invalid/a.png'&gt;"></iframe>
        </body></html>''', encoding="utf-8")
        with self.assertRaises(ValueError):
            builder.build(self.manifest, self.output, force=True)
        self.assertEqual(original, self.output.read_bytes())

    def test_existing_output_is_preserved_and_force_is_explicit(self):
        builder.build(self.manifest, self.output)
        original = self.output.read_bytes()
        self.data["project"] = "New project"
        self.save()
        with self.assertRaises(FileExistsError):
            builder.build(self.manifest, self.output)
        self.assertEqual(original, self.output.read_bytes())
        builder.build(self.manifest, self.output, force=True)
        self.assertNotEqual(original, self.output.read_bytes())

    def test_invalid_resource_keeps_prior_output_even_with_force(self):
        builder.build(self.manifest, self.output)
        original = self.output.read_bytes()
        self.source.write_text('<html><head></head><body><img src="missing.png"></body></html>', encoding="utf-8")
        with self.assertRaises(ValueError):
            builder.build(self.manifest, self.output, force=True)
        self.assertEqual(original, self.output.read_bytes())

    def test_duplicate_identifier_and_invalid_colors(self):
        self.data["candidates"].append(self.data["candidates"][0].copy())
        self.save()
        with self.assertRaises(ValueError):
            builder.build(self.manifest, self.output)
        self.data["candidates"].pop()
        self.data["candidates"][0]["palette"] = ["url(example)"]
        self.save()
        with self.assertRaises(ValueError):
            builder.build(self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_text_and_preserved_script_are_not_css_resources(self):
        self.source.write_text('''<html><head><style>
        /* @import "unused.css"; */
        p::after {content: "example url(example.png) @import"}
        </style></head><body><p>Explain @import and url(example.png)</p>
        <script>const example = "url(unused.png)";</script></body></html>''', encoding="utf-8")
        builder.build(self.manifest, self.output)
        self.assertTrue(self.output.is_file())

    def test_css_sources_are_checked_in_styles_and_inline_attributes(self):
        fragments = [
            '<style>.hero{background:image-set("https://example.invalid/a.png" 1x)}</style>',
            '<style>.hero{background:-webkit-image-set("missing.png" 1x)}</style>',
            '<style>.hero{background:u\\72l(missing.png)}</style>',
            '<style>@import "missing.css";</style>',
        ]
        for fragment in fragments:
            with self.subTest(fragment=fragment):
                self.source.write_text(f'<html><head>{fragment}</head><body>content</body></html>', encoding="utf-8")
                with self.assertRaises(ValueError):
                    builder.build(self.manifest, self.output)
        self.source.write_text('<html><head></head><body style="background:url(missing.png)">content</body></html>', encoding="utf-8")
        with self.assertRaises(ValueError):
            builder.build(self.manifest, self.output)

    def test_source_escape_and_overwriting_inputs_are_rejected(self):
        self.data["candidates"][0]["source"] = "../outside.html"
        self.save()
        with self.assertRaises(ValueError):
            builder.build(self.manifest, self.output)
        self.data["candidates"][0]["source"] = "sample.html"
        self.save()
        with self.assertRaises(ValueError):
            builder.build(self.manifest, self.source, force=True)
        with self.assertRaises(ValueError):
            builder.build(self.manifest, self.manifest, force=True)

    def test_static_image_embedded_and_content_changes_identity(self):
        image = self.folder / "preview.png"
        image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j7ioAAAAASUVORK5CYII='))
        self.data["candidates"][0].update(kind="image", source="preview.png")
        self.save()
        first = builder.build(self.manifest, self.output)
        self.assertIn("data:image/png;base64,", self.output.read_text(encoding="utf-8"))
        self.data["round"] = "02"
        self.save()
        second = builder.build(self.manifest, self.output, force=True)
        self.assertNotEqual(first["fingerprint"], second["fingerprint"])

    def test_relative_local_assets_are_embedded(self):
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
        (self.folder / "pages" / "img").mkdir(parents=True)
        (self.folder / "pages" / "img" / "dot.png").write_bytes(png)
        (self.folder / "pages" / "a.html").write_text('<!doctype html><html><head><style>.x{background:url("img/dot.png")}</style></head><body><img src="img/dot.png" alt=""></body></html>', encoding="utf-8")
        self.data["candidates"][0]["source"] = "pages/a.html"
        self.save()
        builder.build(self.manifest, self.output)
        page = self.output.read_text(encoding="utf-8")
        self.assertNotIn("img/dot.png", page)
        self.assertIn("data:image/png;base64,", page)

    def test_local_assets_outside_the_manifest_folder_stay_rejected(self):
        outside = Path(self.tmp.name).parent / f"{Path(self.tmp.name).name}-outside.png"
        outside.write_bytes(b"\x89PNG\r\n\x1a\n")
        self.addCleanup(outside.unlink)
        self.source.write_text(f'<!doctype html><html><head></head><body><img src="../{outside.name}" alt=""><img src="https://example.com/a.png" alt=""></body></html>', encoding="utf-8")
        with self.assertRaises(ValueError):
            builder.build(self.manifest, self.output)

    def test_live_candidates_accept_only_local_dev_servers(self):
        self.data["candidates"].append({"id": "live", "name": "Current", "concept": "The current version", "typography": "System font", "palette": ["#fff"], "traits": ["Existing page"], "kind": "url", "url": "http://localhost:5173/orders", "baseline": True})
        self.save()
        builder.build(self.manifest, self.output)
        page = self.output.read_text(encoding="utf-8")
        payload = json.loads(page.split("const DATA = ", 1)[1].split(";\n", 1)[0])
        self.assertEqual([c["id"] for c in payload["candidates"]], ["live", "a"])
        for url in ("https://example.com/", "file:///etc/passwd", "http://user:pw@localhost:3000/"):
            self.data["candidates"][1]["url"] = url
            self.save()
            with self.assertRaises(ValueError):
                builder.build(self.manifest, self.output, force=True)

    def test_serve_accepts_command_and_optional_absolute_cwd_and_local_url(self):
        for serve in (
            {"command": "pnpm dev"},
            {"command": "pnpm dev", "cwd": str(self.folder)},
            {"command": "pnpm dev", "cwd": str(self.folder), "url": "http://localhost:3456"},
            {"command": "pnpm dev", "url": "https://127.0.0.1:3456/"},
            {"command": "pnpm dev", "url": "http://[::1]:3456/"},
        ):
            with self.subTest(serve=serve):
                self.data["serve"] = serve
                self.save()
                builder.build(self.manifest, self.output, force=True)
                page = self.output.read_text(encoding="utf-8")
                payload = json.loads(page.split("const DATA = ", 1)[1].split(";\n", 1)[0])
                self.assertEqual(payload["serve"], serve)

    def test_serve_requires_a_nonempty_string_command(self):
        for serve in ({}, {"command": ""}, {"command": "  "}, {"command": 123}, {"command": None}):
            with self.subTest(serve=serve):
                self.data["serve"] = serve
                self.save()
                with self.assertRaisesRegex(ValueError, "serve.command must be a non-empty string"):
                    builder.build(self.manifest, self.output)
        for serve in (None, [], "pnpm dev"):
            with self.subTest(serve=serve):
                self.data["serve"] = serve
                self.save()
                with self.assertRaisesRegex(ValueError, "serve must be an object"):
                    builder.build(self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_serve_cwd_must_be_an_absolute_path(self):
        for cwd in ("project", "./project", "~/project", "", None, 123):
            with self.subTest(cwd=cwd):
                self.data["serve"] = {"command": "pnpm dev", "cwd": cwd}
                self.save()
                with self.assertRaisesRegex(ValueError, "serve.cwd must be an absolute path"):
                    builder.build(self.manifest, self.output)

    def test_serve_url_must_be_local_http_or_https(self):
        for url in ("https://example.com/", "file:///tmp/index.html", "ftp://localhost/", "http://user:pw@localhost:3456/", "http://localhost:bad/", "http://[::1", "", None, 123):
            with self.subTest(url=url):
                self.data["serve"] = {"command": "pnpm dev", "url": url}
                self.save()
                with self.assertRaisesRegex(ValueError, "serve.*url.*local"):
                    builder.build(self.manifest, self.output)

    def test_serve_is_embedded_unchanged_without_script_escape(self):
        serve = {"command": "  printf '</script><script>window.injected=true</script>'\u2028\u2029  ", "cwd": str(self.folder / 'a"$`\\b'), "url": "http://localhost:3456", "note": "extra metadata is kept"}
        self.data["serve"] = serve
        self.save()
        builder.build(self.manifest, self.output)
        page = self.output.read_text(encoding="utf-8")
        payload = json.loads(page.split("const DATA = ", 1)[1].split(";\n", 1)[0])
        self.assertEqual(payload["serve"], serve)
        self.assertNotIn(serve["command"], page)
        self.assertIn('\\u003c/script>', page)
        self.assertIn('\\u2028\\u2029', page)

    def test_url_candidates_without_serve_warn_but_still_build(self):
        self.data["candidates"][0].update(kind="url", url="http://localhost:3456/")
        self.save()
        messages = io.StringIO()
        with redirect_stderr(messages):
            builder.build(self.manifest, self.output)
        self.assertTrue(self.output.is_file())
        self.assertEqual(len(messages.getvalue().splitlines()), 1)
        self.assertIn("Add a top-level serve entry", messages.getvalue())
        self.data["serve"] = {"command": "pnpm dev"}
        self.save()
        messages = io.StringIO()
        with redirect_stderr(messages):
            builder.build(self.manifest, self.output, force=True)
        self.assertEqual(messages.getvalue(), "")

    def test_shell_connections_allow_only_this_rounds_candidate_origins(self):
        self.data["serve"] = {"command": "pnpm dev", "url": "http://localhost:9999/"}
        urls = ["http://localhost:3456/a?note=\"<script>", "http://localhost:3456/b", "https://127.0.0.1:4443/", "http://[::1]:5173/"]
        self.data["candidates"] = [dict(self.data["candidates"][0], id=f"live{i}", kind="url", url=url) for i, url in enumerate(urls)]
        self.save()
        builder.build(self.manifest, self.output)
        policies = []
        class Policies(HTMLParser):
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy":
                    policies.append(attrs["content"])
        Policies().feed(self.output.read_text(encoding="utf-8"))
        self.assertEqual(policies, ["connect-src http://localhost:3456 http://localhost:5173 https://127.0.0.1:4443"])
        self.data["candidates"] = [dict(self.data["candidates"][0], kind="html")]
        self.save()
        builder.build(self.manifest, self.output, force=True)
        self.assertIn('content="connect-src \'none\'"', self.output.read_text(encoding="utf-8"))

    def test_interactive_html_runs_inline_scripts_only_when_asked(self):
        self.assertIn("script-src 'none'", builder.prepare_html(self.source))
        csp = builder.prepare_html(self.source, interactive=True)
        self.assertIn("script-src 'unsafe-inline'", csp)
        self.assertIn("localStorage", csp)
        self.assertNotIn("localStorage", builder.prepare_html(self.source))
        self.assertIn("default-src 'none'", csp)
        self.data["candidates"][0]["interactive"] = True
        self.save()
        builder.build(self.manifest, self.output)
        self.source.write_text('<html><head><script src="https://example.invalid/a.js"></script></head><body></body></html>', encoding="utf-8")
        with self.assertRaises(ValueError):
            builder.build(self.manifest, self.output, force=True)
        self.data["candidates"][0].update(kind="image", interactive=True)
        self.save()
        with self.assertRaises(ValueError):
            builder.build(self.manifest, self.output, force=True)

    def test_local_stylesheets_and_scripts_are_inlined(self):
        (self.folder / "vendor").mkdir()
        (self.folder / "vendor" / "lib.js").write_text("window.lib='</script>'", encoding="utf-8")
        (self.folder / "app.css").write_text("body{color:#123}", encoding="utf-8")
        self.source.write_text('<!doctype html><html><head><link rel="stylesheet" href="app.css">'
                               '<script defer src="vendor/lib.js"></script></head><body><p>Content</p></body></html>', encoding="utf-8")
        static = builder.prepare_html(self.source, root=self.folder)
        self.assertIn("<style>body{color:#123}</style>", static)
        self.assertNotIn("lib.js", static)
        self.assertNotIn("window.lib", static)
        live = builder.prepare_html(self.source, interactive=True, root=self.folder)
        self.assertIn("'unsafe-eval'", live)
        self.assertLess(live.index("<p>Content</p>"), live.index("window.lib"))
        self.assertIn("<\\/script>", live)
        self.data["candidates"][0]["interactive"] = True
        self.save()
        builder.build(self.manifest, self.output)

    def test_only_one_baseline(self):
        second = dict(self.data["candidates"][0], id="b", baseline=True)
        self.data["candidates"][0]["baseline"] = True
        self.data["candidates"].append(second)
        self.save()
        with self.assertRaises(ValueError):
            builder.build(self.manifest, self.output)

    def test_template_keeps_documented_comparison_features(self):
        builder.build(self.manifest, self.output)
        page = self.output.read_text(encoding="utf-8")
        hooks = {
            "compare and single view": 'data-layout="loupe"',
            "mobile viewport": 'data-viewport="mobile"',
            "actual size": 'Actual size (100%)',
            "select": "st.chosen",
            "select copies": 'navigator.clipboard',
            "live url candidates": "c.kind==='url'",
            "dev server down notice": "The dev server isn't running",
            "copy start command": "button.dataset.copyServe",
            "current baseline": "c.baseline",
            "interactive previews": "c.interactive",
            "saved per round": "DATA.fingerprint",
            "shows the north star": "c.concept",
            "shows the palette": "c.palette",
        }
        missing = [name for name, hook in hooks.items() if hook not in page]
        self.assertEqual(missing, [], "the template lacks a feature the comparison page promises")
        for removed in ('class="bar-r"', 'id="round"', 'id="filter-list"', 'id="notes-toggle"',
                        'id="notes"', 'id="show-all"', "liveSource", "imageSource", "interactiveSource", "htmlSource"):
            self.assertNotIn(removed, page)

    def test_brand_assets_and_edition_survive_relocation(self):
        copy = self.folder / "relocated"
        shutil.copytree(ROOT / "scripts", copy / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "assets", copy / "assets")
        logo = "data:image/png;base64," + base64.b64encode((ROOT / "assets/logo.png").read_bytes()).decode("ascii")
        font = "data:font/ttf;base64," + base64.b64encode((ROOT / "assets/fonts/instrument-serif/InstrumentSerif-Regular.ttf").read_bytes()).decode("ascii")
        for name, edition in (("oil-ui-pro", "pro"), ("oil-ui", "open")):
            with self.subTest(edition=edition):
                (copy / "SKILL.md").write_text("---\nname: " + name + "\n---\n", encoding="utf-8")
                output = self.folder / (edition + ".html")
                run = subprocess.run([sys.executable, str(copy / "scripts/build_explorer.py"), str(self.manifest),
                                      "--output", str(output)], cwd=self.folder, capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
                page = output.read_text(encoding="utf-8")
                self.assertEqual(self.payload(page)["edition"], edition)
                self.assertIn(logo, page)
                self.assertIn(font, page)
                self.assertNotIn('href="logo.png"', page)
                self.assertNotIn('src="logo.png"', page)
                self.assertNotIn('url("fonts/', page)

    def test_copied_skill_works_from_another_directory(self):
        copy = self.folder / "relocated"
        shutil.copytree(ROOT / "scripts", copy / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "assets", copy / "assets")
        run = subprocess.run([sys.executable, str(copy / "scripts" / "build_explorer.py"), str(self.manifest), "--output", str(self.output)], cwd=self.folder, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(self.output.is_file())


if __name__ == "__main__":
    unittest.main()
