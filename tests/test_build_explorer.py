"""Observable builder contracts. Run with Python's unittest discovery."""

import base64
from contextlib import redirect_stderr
import importlib.util
from html.parser import HTMLParser
import io
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote


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
        self.source.write_text('<!doctype html><html><head><style>body{color:#123}</style></head><body>同一内容<script>window.bad=true</script></body></html>', encoding="utf-8")
        self.data = {"schemaVersion": 1, "project": "项目", "brief": "同一内容比较", "round": "01", "candidates": [{"id": "a", "name": "方向一", "concept": "编辑式", "typography": "宋体与黑体", "palette": ["#112233", "#fff"], "traits": ["大标题"], "kind": "html", "source": "sample.html"}]}
        self.save()

    def save(self):
        self.manifest.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

    def payload(self, page):
        return json.loads(page.split("const DATA = ", 1)[1].split(";\n", 1)[0])

    def run_browser_probe(self, result_id="i18n-result", profile="chrome-probe"):
        chrome = (shutil.which("google-chrome") or shutil.which("chromium") or
                  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
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
        runner = runner.replace("#i18n-result", "#" + result_id)
        return subprocess.run([shutil.which("node"), "--input-type=module", "-e", runner, chrome,
                               str(self.folder / profile), self.output.as_uri()],
                              capture_output=True, text=True, timeout=25, encoding="utf-8")

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

    def test_native_viewport_formats_are_normalized_and_equivalent(self):
        fingerprints = set()
        for value in ("1920x1080", "1920×1080", " 1920 X 1080 ",
                      {"width": 1920, "height": 1080}, {"width": 1920.0, "height": 1080.0}):
            for top_level in (True, False):
                with self.subTest(value=value, top_level=top_level):
                    self.data.pop("nativeViewport", None)
                    self.data["candidates"][0].pop("nativeViewport", None)
                    target = self.data if top_level else self.data["candidates"][0]
                    target["nativeViewport"] = value
                    self.save()
                    fingerprints.add(builder.build(self.manifest, self.output, force=True)["fingerprint"])
                    payload = self.payload(self.output.read_text(encoding="utf-8"))
                    self.assertEqual(payload["candidates"][0]["nativeViewport"], {"width": 1920, "height": 1080})
        self.assertEqual(len(fingerprints), 1)

    def test_native_viewport_inheritance_override_and_identity(self):
        default = builder.build(self.manifest, self.output)
        self.assertNotIn("nativeViewport", self.payload(self.output.read_text(encoding="utf-8"))["candidates"][0])
        self.data["nativeViewport"] = "1920x720"
        self.data["candidates"].extend([
            dict(self.data["candidates"][0], id="b", nativeViewport={"width": 1366, "height": 1024}),
            dict(self.data["candidates"][0], id="c", nativeViewport="198×242"),
        ])
        self.save()
        result = builder.build(self.manifest, self.output, force=True)
        candidates = self.payload(self.output.read_text(encoding="utf-8"))["candidates"]
        self.assertEqual([c["nativeViewport"] for c in candidates], [
            {"width": 1920, "height": 720}, {"width": 1366, "height": 1024}, {"width": 198, "height": 242}])
        self.assertNotEqual(result["fingerprint"], default["fingerprint"])
        self.data["candidates"][0]["nativeViewport"] = "1920x1080"
        self.save()
        self.assertNotEqual(builder.build(self.manifest, self.output, force=True)["fingerprint"], result["fingerprint"])

    def test_invalid_native_viewports_report_received_values_and_preserve_output(self):
        builder.build(self.manifest, self.output)
        original = self.output.read_bytes()
        invalid = (None, True, 1920, [], {}, "", "1920", "1920:1080", "-1x1080", "0×1080",
                   "1920.5x1080", {"width": 1920}, {"width": "1920", "height": 1080},
                   {"width": True, "height": 1080}, {"width": 1920, "height": 0},
                   {"width": 1920, "height": 1.5})
        for value in invalid:
            for top_level in (True, False):
                with self.subTest(value=value, top_level=top_level):
                    self.data.pop("nativeViewport", None)
                    self.data["candidates"][0].pop("nativeViewport", None)
                    target = self.data if top_level else self.data["candidates"][0]
                    target["nativeViewport"] = value
                    self.save()
                    with self.assertRaises(builder.ManifestError) as caught:
                        builder.build(self.manifest, self.output, force=True)
                    message = str(caught.exception)
                    for expected in ("候选 a", "nativeViewport", json.dumps(value, ensure_ascii=False),
                                     '"1920x1080"', '"1920×1080"', '{"width":1920,"height":1080}'):
                        self.assertIn(expected, message)
                    self.assertEqual(self.output.read_bytes(), original)

    def test_native_viewport_errors_are_collected_with_other_manifest_problems(self):
        self.data["nativeViewport"] = "bad-default"
        self.data["candidates"].append(dict(self.data["candidates"][0], id="b", nativeViewport="bad-b", palette=["red"]))
        self.data["candidates"].append(dict(self.data["candidates"][0], id="c", nativeViewport={"height": 242}))
        self.save()
        with self.assertRaises(builder.ManifestError) as caught:
            builder.build(self.manifest, self.output)
        self.assertEqual(len(caught.exception.problems), 4)
        for expected in ("manifest（用于候选 a）", "bad-default", "候选 b：nativeViewport", "bad-b",
                         "候选 b：palette", "候选 c：nativeViewport", '{"height": 242}'):
            self.assertIn(expected, str(caught.exception))

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed to execute preview fitting")
    def test_default_viewports_and_narrow_native_canvas_fitting(self):
        template = builder.TEMPLATE.read_text(encoding="utf-8")
        fit = template.split(" function fit(s){", 1)[1].split("\n const fitAll=", 1)[0]
        program = r"""
const SIZES={desktop:{w:1280,h:900},mobile:{w:390,h:844}},st={viewport:'desktop'};
const byId={a:{}},innerHeight=844,$=()=>({offsetHeight:100});
const narrow=()=>true,getComputedStyle=()=>({paddingLeft:'12',paddingRight:'12',paddingTop:'16',paddingBottom:'16'});
const m={style:{}},box={clientWidth:390,clientHeight:0,dataset:{zoom:'fit'},classList:{contains:()=>false}};
const s={isConnected:true,dataset:{id:'a'},parentElement:box,querySelector:()=>m,style:{}};
""" + "function fit(s){" + fit + r"""
const result=[];
fit(s);result.push({...m.style,stage:{...s.style}});
st.viewport='mobile';fit(s);result.push({...m.style,stage:{...s.style}});
byId.a.nativeViewport={width:198,height:242};fit(s);result.push({...m.style,stage:{...s.style}});
byId.a.nativeViewport={width:1366,height:1024};box.classList.contains=()=>true;
fit(s);result.push({...m.style,stage:{...s.style}});
byId.a.nativeViewport={width:198,height:2000};fit(s);result.push({...m.style,stage:{...s.style}});
box.dataset.zoom='actual';fit(s);result.push({...m.style,stage:{...s.style}});
console.log(JSON.stringify(result));
"""
        run = subprocess.run([shutil.which("node"), "-e", program], capture_output=True, text=True, timeout=10, encoding="utf-8")
        self.assertEqual(run.returncode, 0, run.stderr)
        results = json.loads(run.stdout)
        for result, (width, height, scale) in zip(results, [
                (1280, 900, 390 / 1280), (390, 844, 1), (198, 242, 1),
                (1366, 1024, 366 / 1366), (198, 2000, 712 / 2000), (198, 2000, 1)]):
            self.assertEqual(result["width"], f"{width}px")
            self.assertEqual(result["height"], f"{height}px")
            self.assertAlmostEqual(float(result["transform"][6:-1]), scale)
            self.assertAlmostEqual(float(result["stage"]["width"][:-2]), width * scale)
            self.assertAlmostEqual(float(result["stage"]["height"][:-2]), height * scale)

    @unittest.skipUnless(shutil.which("node") and (shutil.which("google-chrome") or shutil.which("chromium") or
                         Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome").is_file()),
                         "Chrome/Chromium is needed for rendered viewport checks")
    def test_rendered_native_viewports_fit_cards_loupe_and_actual_size(self):
        self.data["nativeViewport"] = "1920x1080"
        self.data["candidates"].extend([
            dict(self.data["candidates"][0], id="b", nativeViewport="1920×720"),
            dict(self.data["candidates"][0], id="c", nativeViewport={"width": 198, "height": 242}),
        ])
        self.save()
        builder.build(self.manifest, self.output)
        probe = r"""<script>
(async()=>{
 const tick=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
 const measure=s=>{
  const m=s.querySelector('iframe'),r=m.getBoundingClientRect(),b=s.getBoundingClientRect();
  const box=s.parentElement,cs=getComputedStyle(box);
  return {id:s.dataset.id,width:parseFloat(m.style.width),height:parseFloat(m.style.height),
   scale:new DOMMatrix(getComputedStyle(m).transform).a,stage:[b.width,b.height],media:[r.width,r.height],
   available:[box.clientWidth-parseFloat(cs.paddingLeft)-parseFloat(cs.paddingRight),
              box.clientHeight-parseFloat(cs.paddingTop)-parseFloat(cs.paddingBottom)]};
 };
 await tick();const cards=[...document.querySelectorAll('.card .stage')].map(measure);
 document.querySelector('[data-viewport=mobile]').click();await tick();
 const mobile=[...document.querySelectorAll('.card .stage')].map(measure);
 const loupe=[],actual=[];
 for(const card of document.querySelectorAll('.card')){
  card.querySelector('.hit').click();await tick();
  loupe.push(measure(document.querySelector('.slide.is-current .stage')));
  document.querySelector('#zoom').click();await tick();
  actual.push(measure(document.querySelector('.slide.is-current .stage')));
  document.querySelector('[data-layout=compare]').click();await tick();
 }
 const out=document.createElement('pre');out.id='viewport-result';
 out.textContent=JSON.stringify({cards,mobile,loupe,actual});document.body.append(out);
})();
</script>"""
        self.output.write_text(self.output.read_text(encoding="utf-8").replace("</body></html>", probe + "</body></html>"), encoding="utf-8")
        run = self.run_browser_probe("viewport-result", "chrome-native")
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        sizes = {"a": (1920, 1080), "b": (1920, 720), "c": (198, 242)}
        for mode, samples in result.items():
            self.assertEqual(len(samples), 3, mode)
            for sample in samples:
                with self.subTest(mode=mode, id=sample["id"]):
                    width, height = sizes[sample["id"]]
                    self.assertEqual((sample["width"], sample["height"]), (width, height))
                    scale = sample["scale"]
                    self.assertGreater(scale, 0)
                    self.assertLessEqual(scale, 1)
                    if mode == "actual":
                        self.assertEqual(scale, 1)
                    else:
                        self.assertLessEqual(sample["stage"][0], sample["available"][0] + .1)
                        if mode == "loupe":
                            self.assertLessEqual(sample["stage"][1], sample["available"][1] + .1)
                    for dimension, native in enumerate((width, height)):
                        self.assertAlmostEqual(sample["stage"][dimension], native * scale, delta=.1)
                        self.assertAlmostEqual(sample["media"][dimension], native * scale, delta=.1)

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
        # Passed as a file: the program is longer than a Windows command line may be.
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "program.cjs"
            script.write_text(program, encoding="utf-8")
            run = subprocess.run([shutil.which("node"), str(script)], capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        results = iter(json.loads(run.stdout))
        for _, _, expected in cases:
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
                run = self.run_browser_probe(profile="chrome-" + lang)
                self.assertEqual(run.returncode, 0, run.stderr)
                observed = json.loads(run.stdout)
                self.assertEqual(observed["lang"], table[lang]["htmlLang"])
                self.assertEqual(observed["title"], table[lang]["projectTitle"].replace("{project}", "Demo").replace("{edition}", " Pro" if self.payload(page)["edition"] == "pro" else ""))
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
                self.assertEqual(observed["copied"], ["01：选 现状 Direction A"] if lang == "zh"
                                 else ["Round 01: Go with Current Direction A"])

    def test_portable_single_file_and_html_payload(self):
        result = builder.build(self.manifest, self.output)
        page = self.output.read_text(encoding="utf-8")
        self.assertEqual(result["candidates"], 1)
        self.assertIn("同一内容", page)
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
        self.data["project"] = "新项目"
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

    def test_missing_outside_source_and_overwriting_inputs_are_rejected(self):
        self.data["candidates"][0]["source"] = "../outside.html"
        self.save()
        with self.assertRaisesRegex(ValueError, "找不到本地资源.*outside.html"):
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

    def test_local_assets_outside_manifest_are_embedded_and_protected(self):
        with tempfile.TemporaryDirectory() as outside_dir:
            assets = Path(outside_dir).resolve() / "素材 #100%"
            assets.mkdir()
            (assets / "font.ttf").write_bytes(b"local-font")
            (assets / "image.png").write_bytes(b"local-image")
            (assets / "app.js").write_text("window.loaded=true", encoding="utf-8")
            (assets / "app.css").write_text('@font-face{font-family:test;src:url(font.ttf)}', encoding="utf-8")
            # Exercise ../ traversal as well as absolute references; no file copying is needed.
            relative = quote(Path(os.path.relpath(assets / "app.css", self.folder.resolve())).as_posix())
            self.source.write_text(f'<html><head><link rel="stylesheet" href="{relative}"></head>'
                                   f'<body style="background:url({(assets / "image.png").as_uri()})">'
                                   f'<img src="{(assets / "image.png").as_uri()}">'
                                   f'<script defer src="{(assets / "app.js").as_uri()}"></script></body></html>', encoding="utf-8")
            self.data["candidates"][0]["interactive"] = True
            self.save()
            first = builder.build(self.manifest, self.output)
            content = self.payload(self.output.read_text(encoding="utf-8"))["candidates"][0]["content"]
            self.assertIn("data:font/ttf;base64," + base64.b64encode(b"local-font").decode(), content)
            self.assertEqual(content.count("data:image/png;base64,"), 2)
            self.assertIn("window.loaded=true", content)
            self.assertNotIn(str(assets), content)
            original = {p: p.read_bytes() for p in assets.iterdir()}
            for path in original:
                with self.subTest(overwrite=path.name), self.assertRaisesRegex(ValueError, "输出不能覆盖输入"):
                    builder.build(self.manifest, path, force=True)
                self.assertEqual(path.read_bytes(), original[path])
            (assets / "font.ttf").write_bytes(b"updated-font")
            second = builder.build(self.manifest, self.output, force=True)
            self.assertNotEqual(first["fingerprint"], second["fingerprint"])

    def test_outside_candidate_source_is_accepted_and_protected(self):
        with tempfile.TemporaryDirectory() as outside_dir:
            source = Path(outside_dir) / "outside.html"
            source.write_text("<p>外部候选</p>", encoding="utf-8")
            self.data["candidates"][0]["source"] = str(source)
            self.save()
            builder.build(self.manifest, self.output)
            self.assertIn("外部候选", self.payload(self.output.read_text(encoding="utf-8"))["candidates"][0]["content"])
            with self.assertRaisesRegex(ValueError, "输出不能覆盖输入"):
                builder.build(self.manifest, source, force=True)

    @unittest.skipUnless(sys.platform == "win32", "Windows drive paths")
    def test_native_windows_resource_paths_accept_slashes_and_reserved_characters(self):
        image = self.folder / "素材 #100%.png"
        image.write_bytes(b"image")
        for ref in (str(image), image.as_posix(), image.as_uri()):
            with self.subTest(ref=ref):
                self.source.write_text(f'<img src="{ref}">', encoding="utf-8")
                builder.build(self.manifest, self.output, force=True)
                content = self.payload(self.output.read_text(encoding="utf-8"))["candidates"][0]["content"]
                self.assertIn("data:image/png;base64,aW1hZ2U=", content)
                self.assertNotIn("#100", content)

    def test_source_filesystem_paths_and_text_newlines_keep_existing_behavior(self):
        source = self.folder / "candidate #1%20.html"
        source.write_bytes(b'<html>\r\n<head></head>\r\n<body>content</body></html>')
        self.data["candidates"][0]["source"] = source.name
        self.save()
        builder.build(self.manifest, self.output)
        content = self.payload(self.output.read_text(encoding="utf-8"))["candidates"][0]["content"]
        self.assertIn("<html>\n<head>", content)
        self.assertNotIn("\r", content)
        self.assertEqual(source.read_bytes(), b'<html>\r\n<head></head>\r\n<body>content</body></html>')

    def test_css_imports_resolve_relative_to_each_stylesheet(self):
        (self.folder / "styles" / "nested").mkdir(parents=True)
        (self.folder / "styles" / "main.css").write_text('@import "nested/theme.css" layer(theme) supports(display: grid) screen; body{margin:0}', encoding="utf-8")
        (self.folder / "styles" / "nested" / "theme.css").write_text('@import "../main.css"; @font-face{src:url("../../font.ttf?v=1")} .hero{background:url(../../image.png)}', encoding="utf-8")
        (self.folder / "font.ttf").write_bytes(b"font")
        (self.folder / "image.png").write_bytes(b"image")
        self.source.write_text('<link REL=stylesheet HREF="styles/main.css" media="(min-width: 1px)"><p>内容</p>', encoding="utf-8")
        builder.build(self.manifest, self.output)
        content = self.payload(self.output.read_text(encoding="utf-8"))["candidates"][0]["content"]
        for expected in ("@media (min-width: 1px)", "@layer theme", "@supports (display: grid)", "@media screen", "data:font/ttf;base64,", "data:image/png;base64,"):
            self.assertIn(expected, content)
        self.assertNotIn("@import", content)
        self.assertNotIn("image.png", content)

    def test_resource_spelling_variants_are_embedded(self):
        (self.folder / "图 片.png").write_bytes(b"image")
        (self.folder / "sprite.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><symbol id="dot"/></svg>', encoding="utf-8")
        self.source.write_text(r'''<html><head><style>
          .hero{background:u\72l(/* image */ "图%20片.png?cache=1")}
          .retina{background:image-set("图%20片.png" 1x, url("图%20片.png") 2x)}
        </style></head><body><IMG SRC=图%20片.png><svg><use href="sprite.svg#dot"/></svg>
        <video poster="图%20片.png"></video></body></html>''', encoding="utf-8")
        builder.build(self.manifest, self.output)
        content = self.payload(self.output.read_text(encoding="utf-8"))["candidates"][0]["content"]
        self.assertEqual(content.count("data:image/png;base64,"), 5)
        self.assertIn("data:image/svg+xml;base64,", content)
        self.assertIn('#dot"', content)
        self.assertNotIn("图%20片.png", content)

    def test_img_srcset_keeps_src_or_takes_the_widest_candidate(self):
        (self.folder / "small.png").write_bytes(b"small")
        (self.folder / "large.png").write_bytes(b"large-image")
        cases = {
            '<img src="small.png" srcset="small.png 600w, large.png 1200w" alt="">': b"small",
            '<img srcset="small.png 600w, large.png 1200w" alt="">': b"large-image",
            '<img srcset="large.png 2x, small.png" alt="">': b"large-image",
        }
        for tag, expected in cases.items():
            with self.subTest(tag=tag):
                self.source.write_text(f"<html><head></head><body>{tag}</body></html>", encoding="utf-8")
                builder.build(self.manifest, self.output, force=True)
                content = self.payload(self.output.read_text(encoding="utf-8"))["candidates"][0]["content"]
                self.assertNotIn("srcset", content)
                self.assertEqual(content.count("data:image/png;base64,"), 1)
                self.assertIn('src="data:image/png;base64,' + base64.b64encode(expected).decode(), content)
        # A data URL keeps its commas, and an empty src gives way instead of leaving two src attributes.
        inline = "data:image/png;base64,QUFB,QkI="
        for tag, expected in {f'<img srcset="{inline} 2x, small.png 1x" alt="">': inline,
                              '<img src="" srcset="large.png 1200w" alt="">': "data:image/png;base64," + base64.b64encode(b"large-image").decode()}.items():
            with self.subTest(tag=tag):
                self.source.write_text(f"<html><head></head><body>{tag}</body></html>", encoding="utf-8")
                builder.build(self.manifest, self.output, force=True)
                content = self.payload(self.output.read_text(encoding="utf-8"))["candidates"][0]["content"]
                img = re.search(r"<img[^>]*>", content)[0]
                self.assertEqual(re.findall(r'\ssrc="([^"]*)"', img), [expected])
                self.assertNotIn("srcset", img)

    def test_shell_secondary_text_meets_body_contrast(self):
        template = (ROOT / "assets" / "style-explorer.html").read_text(encoding="utf-8")
        tokens = dict(re.findall(r"--(canvas|well|faint|soft):(#[0-9a-f]{6})", re.search(r":root\{([^}]*)\}", template)[1]))

        def luminance(color):
            channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
            return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

        for text in ("faint", "soft"):
            for ground in ("canvas", "well"):
                with self.subTest(text=text, ground=ground):
                    high, low = sorted((luminance(tokens[text]), luminance(tokens[ground])), reverse=True)
                    self.assertGreaterEqual((high + 0.05) / (low + 0.05), 4.5)

    def test_resource_examples_in_text_comments_and_scripts_stay_unchanged(self):
        example = '<img src="missing.png"> url(missing.png)'
        self.source.write_text(f'<html><head><style>/* url(missing.png) */ p::after{{content:\'url(missing.png)\'}}</style></head>'
                               f'<body><!-- {example} --><script>const example = \'{example}\';</script></body></html>', encoding="utf-8")
        content = builder.prepare_html(self.source, interactive=True)
        self.assertIn(example, content)
        self.assertIn("/* url(missing.png) */", content)
        self.assertIn("content:'url(missing.png)'", content)

    def test_remote_and_missing_resources_report_exact_reference_and_fix(self):
        for ref in ("https://example.invalid/font.ttf", "//example.invalid/font.ttf", "missing.ttf"):
            for fragment in (f'<img src="{ref}">', f'<style>@font-face{{src:url("{ref}")}}</style>',
                             f'<link rel="stylesheet" href="{ref}">', f'<script src="{ref}"></script>'):
                with self.subTest(ref=ref, fragment=fragment):
                    self.source.write_text(fragment, encoding="utf-8")
                    with self.assertRaises(builder.ManifestError) as caught:
                        builder.build(self.manifest, self.output)
                    message = str(caught.exception)
                    for expected in ("候选 a", "sample.html", ref, "重新生成"):
                        self.assertIn(expected, message)
                    self.assertIn("curl -L --fail --output" if "example.invalid" in ref else "请将该文件保存到", message)
                    self.assertFalse(self.output.exists())

    def test_resource_size_limits_preserve_output_and_allow_the_boundary(self):
        builder.build(self.manifest, self.output)
        original = self.output.read_bytes()
        image = self.folder / "large.png"
        image.write_bytes(b"i" * 1025)
        self.source.write_text('<img src="large.png">', encoding="utf-8")
        with patch.object(builder, "MAX_RESOURCE_BYTES", 1024):
            with self.assertRaisesRegex(ValueError, "large.png.*单文件上限 1024.*压缩"):
                builder.build(self.manifest, self.output, force=True)
        self.assertEqual(self.output.read_bytes(), original)
        used = set()
        image.write_bytes(b"i" * 1024)
        with patch.object(builder, "MAX_RESOURCE_BYTES", 1024), patch.object(builder, "MAX_TOTAL_RESOURCE_BYTES", 1024):
            self.assertEqual(len(builder.read_asset(image, used)), 1024)
            builder.read_asset(image, used)  # Repeated references count as one input.
            other = self.folder / "other.png"
            other.write_bytes(b"i")
            with self.assertRaisesRegex(ValueError, "累计.*总上限 1024.*压缩"):
                builder.read_asset(other, used)
        with patch.object(builder, "MAX_TOTAL_RESOURCE_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "总上限"):
                builder.build(self.manifest, self.output, force=True)
        self.assertEqual(self.output.read_bytes(), original)

    def test_palette_extracts_hex_colors_from_descriptions_and_other_shapes(self):
        examples = [
            (["深墨绿 #1b3a2a 实色带", "白色 #FFF"], ["#1b3a2a", "#FFF"]),
            ("深墨绿 #1b3a2a，白色 #FFF", ["#1b3a2a", "#FFF"]),
            ({"主色": "#1b3a2a", "背景": "白色 #FFF"}, ["#1b3a2a", "#FFF"]),
            ([None, 42, {"color": "#1234"}, "#12345678 #abc"], ["#1234", "#12345678", "#abc"]),
            (["red", "#fff"], ["#fff"]),
        ]
        for value, expected in examples:
            with self.subTest(value=value):
                self.data["candidates"][0]["palette"] = value
                self.save()
                builder.build(self.manifest, self.output, force=True)
                self.assertEqual(self.payload(self.output.read_text(encoding="utf-8"))["candidates"][0]["palette"], expected)

    def test_palette_without_any_complete_hex_color_has_copyable_fix(self):
        for value in (None, 123, [], {}, ["green"], "#12 #12345 #1234567 #123456789 #12345g"):
            with self.subTest(value=value):
                self.data["candidates"][0]["palette"] = value
                self.save()
                with self.assertRaisesRegex(ValueError, r'候选 a：palette.*"palette": \["#1a2b3c", "#ffffff"\]'):
                    builder.build(self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_missing_or_unclosed_head_is_completed_before_csp(self):
        examples = [
            '<!doctype html><html><body><p>内容</p></body></html>',
            '<!doctype html><p>内容</p>',
            '<body><p>内容</p></body>',
            '<html><head/><body><p>内容</p></body></html>',
            '<!-- <head>假标签</head> --><p>内容</p>',
            '<html><head><style>p{color:red}</style><body><p>内容</p></body></html>',
            '<html><head><title>内容</title></html>',
        ]
        for source in examples:
            for interactive in (False, True):
                with self.subTest(source=source, interactive=interactive):
                    self.source.write_text(source, encoding="utf-8")
                    content = builder.prepare_html(self.source, interactive=interactive)
                    self.assertIn("内容", content)
                    self.assertIn("</head>", content)
                    observed = []
                    class Tags(HTMLParser):
                        def handle_starttag(self, tag, attrs):
                            observed.append(tag)
                    Tags().feed(content)
                    head = observed.index("head")
                    self.assertEqual(observed[head + 1], "meta")
                    self.assertLess(content.index("Content-Security-Policy"), content.index("</head>"))
                    self.assertEqual(self.source.read_text(encoding="utf-8"), source)

    @unittest.skipUnless(shutil.which("node") and (shutil.which("google-chrome") or shutil.which("chromium") or
                         Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome").is_file()),
                         "Chrome/Chromium is needed for offline resource rendering")
    def test_rendered_inlined_assets_and_completed_head_work_offline(self):
        image = self.folder / "image.png"
        image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j7ioAAAAASUVORK5CYII='))
        font = ROOT / "assets/fonts/instrument-serif/InstrumentSerif-Regular.ttf"
        self.source.write_text(f'''<style>@font-face{{font-family:Test;src:url("{font.as_uri()}")}}
          p{{font-family:Test}}</style><p>Offline font</p><img src="image.png">
          <script>window.addEventListener('load',async()=>{{await document.fonts.load('16px Test');await document.fonts.ready;
            parent.postMessage({{probe:'offline-assets',image:document.querySelector('img').naturalWidth,
              font:[...document.fonts].every(f=>f.status==='loaded')}},'*');
          }});</script>''', encoding="utf-8")
        self.data["candidates"][0]["interactive"] = True
        self.save()
        builder.build(self.manifest, self.output)
        probe = '''<script>window.addEventListener('message',event=>{
          if(event.data?.probe!=='offline-assets')return;
          const out=document.createElement('pre');out.id='offline-result';
          out.textContent=JSON.stringify(event.data);document.body.append(out);
        });</script>'''
        page = self.output.read_text(encoding="utf-8")
        self.output.write_text(page.replace('<head>', '<head>' + probe, 1), encoding="utf-8")
        run = self.run_browser_probe("offline-result", "chrome-offline")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout), {"probe": "offline-assets", "image": 1, "font": True})

    def test_live_candidates_accept_only_local_dev_servers(self):
        self.data["candidates"].append({"id": "live", "name": "现状", "concept": "当前版本", "typography": "系统字体", "palette": ["#fff"], "traits": ["现有页面"], "kind": "url", "url": "http://localhost:5173/orders", "baseline": True})
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
                with self.assertRaisesRegex(ValueError, "serve.command 必须是非空字符串"):
                    builder.build(self.manifest, self.output)
        for serve in (None, [], "pnpm dev"):
            with self.subTest(serve=serve):
                self.data["serve"] = serve
                self.save()
                with self.assertRaisesRegex(ValueError, "serve 必须是对象"):
                    builder.build(self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_serve_cwd_must_be_an_absolute_path(self):
        for cwd in ("project", "./project", "~/project", "", None, 123):
            with self.subTest(cwd=cwd):
                self.data["serve"] = {"command": "pnpm dev", "cwd": cwd}
                self.save()
                with self.assertRaisesRegex(ValueError, "serve.cwd 必须是绝对路径"):
                    builder.build(self.manifest, self.output)

    def test_serve_url_must_be_local_http_or_https(self):
        for url in ("https://example.com/", "file:///tmp/index.html", "ftp://localhost/", "http://user:pw@localhost:3456/", "http://localhost:bad/", "http://[::1", "", None, 123):
            with self.subTest(url=url):
                self.data["serve"] = {"command": "pnpm dev", "url": url}
                self.save()
                with self.assertRaisesRegex(ValueError, "serve.*url.*本机"):
                    builder.build(self.manifest, self.output)

    def test_serve_is_embedded_unchanged_without_script_escape(self):
        serve = {"command": "  printf '</script><script>window.injected=true</script>'\u2028\u2029  ", "cwd": str(self.folder / 'a"$`\\b'), "url": "http://localhost:3456", "note": "保留额外元数据"}
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
        self.assertIn("建议在 manifest 顶层补上 serve", messages.getvalue())
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
                               '<script defer src="vendor/lib.js"></script></head><body><p>内容</p></body></html>', encoding="utf-8")
        static = builder.prepare_html(self.source, root=self.folder)
        self.assertIn("<style>body{color:#123}</style>", static)
        self.assertNotIn("lib.js", static)
        self.assertNotIn("window.lib", static)
        live = builder.prepare_html(self.source, interactive=True, root=self.folder)
        self.assertIn("'unsafe-eval'", live)
        self.assertLess(live.index("<p>内容</p>"), live.index("window.lib"))
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
            "并排与单张": 'data-layout="loupe"',
            "手机视口": 'data-viewport="mobile"',
            "实际尺寸": '实际尺寸 100%',
            "选择": "st.chosen",
            "选择即复制": 'navigator.clipboard',
            "本地地址候选": "c.kind==='url'",
            "服务未运行提示": "开发服务器没有运行",
            "复制启动命令": "button.dataset.copyServe",
            "现状基线": "c.baseline",
            "可操作小样": "c.interactive",
            "按轮次保存": "DATA.fingerprint",
            "展示北极星": "c.concept",
            "展示色板": "c.palette",
        }
        missing = [name for name, hook in hooks.items() if hook not in page]
        self.assertEqual(missing, [], "模板缺少对比页承诺的功能，见 .github/EXPLORER.md")
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
                                      "--output", str(output)], cwd=self.folder, capture_output=True, text=True, encoding="utf-8")
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
        run = subprocess.run([sys.executable, str(copy / "scripts" / "build_explorer.py"), str(self.manifest), "--output", str(self.output)], cwd=self.folder, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(self.output.is_file())


    def test_every_manifest_problem_is_reported_in_one_pass(self):
        self.data["schemaVersion"] = 2
        self.data["candidates"][0].update(id="A", palette=["red"], source="missing.html")
        self.data["candidates"].append({"id": "b", "concept": "c", "typography": "t", "palette": ["#123456"], "traits": [], "kind": "pdf"})
        self.save()
        with self.assertRaises(builder.ManifestError) as caught:
            builder.build(self.manifest, self.output)
        text = str(caught.exception)
        self.assertGreaterEqual(len(caught.exception.problems), 6)
        for expected in ("schemaVersion", '候选 id "A" 无效', "missing.html", "red", 'kind 只能是', "候选 b：name", "候选 b：traits"):
            self.assertIn(expected, text)
        self.assertFalse(self.output.exists())

    def test_single_problem_reads_as_one_sentence(self):
        self.data["candidates"][0]["palette"] = ["blue"]
        self.save()
        with self.assertRaises(ValueError) as caught:
            builder.build(self.manifest, self.output)
        self.assertNotIn("处要改", str(caught.exception))
        self.assertIn("候选 a：palette", str(caught.exception))

    def test_output_defaults_to_a_file_beside_the_manifest(self):
        run = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_explorer.py"), str(self.manifest)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(run.returncode, 0, run.stderr)
        expected = self.folder.resolve() / "style-explorer.html"
        self.assertEqual(Path(json.loads(run.stdout)["output"]), expected)
        self.assertTrue(expected.is_file())
        again = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_explorer.py"), str(self.manifest)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(again.returncode, 1)
        self.assertIn("--force", again.stderr)

    def test_missing_and_malformed_manifests_say_what_to_do(self):
        script = str(ROOT / "scripts" / "build_explorer.py")
        missing = subprocess.run([sys.executable, script, str(self.folder / "nope.json")], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("找不到 manifest", missing.stderr)
        self.assertNotIn("Errno", missing.stderr)
        broken = self.folder / "broken.json"
        broken.write_text('{"schemaVersion": 1,', encoding="utf-8")
        malformed = subprocess.run([sys.executable, script, str(broken)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(malformed.returncode, 1)
        self.assertRegex(malformed.stderr, r"不是合法的 JSON：第 \d+ 行第 \d+ 列")
        self.assertNotIn("Traceback", malformed.stderr)

    def test_help_shows_a_complete_example(self):
        run = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_explorer.py"), "--help"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(run.returncode, 0)
        for expected in ("manifest.json", '"schemaVersion": 1', "--force", "style-explorer.html"):
            self.assertIn(expected, run.stdout)


if __name__ == "__main__":
    unittest.main()
