# Tools

Call the programs bundled in this directory as written below. There is no need to read their source. Add `--help` to print the same instructions.

When the host has its own browser tools, keep using them to view pages and walk through flows. When you need to hand over the standard evidence listed below, prefer the screenshot tool here: it opens a separate temporary browser and never touches the data in the user's own browser. When the machine lacks Node 22, or has no Chrome, Chromium, or Edge, fall back to the host's tools and hand over the same items. Do not write a separate Playwright or browser-protocol script for screenshots.

## Screenshots and recordings

When the task or project has already specified a screenshot tool, use it and hand over the same evidence: the states required, a 200% detail, and a motion recording or three frames. The tool below fills in what that tool cannot do, such as motion probing.

```text
node <skill>/scripts/shoot.mjs <page URL or HTML file> [options]
```

Local files are opened through a temporary server that listens only on this machine. Quote addresses containing `?` or `&`, for example `"http://127.0.0.1:3000/?state=done"`. Using `--states` is easier. Files with the same name are overwritten directly, no extra flag needed.

| What you want | Add |
| --- | --- |
| One shot per state, then combined into a sheet | `--states idle,running,done,error --sheet` |
| A version with all text masked as well | add `--mask` |
| 200% screenshots | `--zoom 2` |
| One set each for mobile and desktop | `--size 390x844,1280x900` (the default is 390x844 only) |
| Full-page long screenshot | `--full` |
| Pointing out problems to the user: draw boxes on elements and number them | `--mark "1=.page-head .btn; 2=.toggle-row" --full`, which also writes `<state>-marked.png` |
| Perform a few actions before the screenshot | `--steps "click .open; wait 300"` |
| Record the primary action, plus start, middle, and end frames | `--record --steps "drag .handle 0 -80; wait 400; click .start" --hold 1500` |
| Record the first-load entrance, starting from the page's first paint | `--record --entry --hold 1500` |
| Motion probe: whether first load, the primary action, and scrolling top to bottom animate, and how much | `--motion --size 1440x900 --steps "click .primary"` |
| Screenshot recreation: side by side and overlaid with the reference, plus a difference heatmap | `--compare reference.png --size <the reference's logical size>` |

Each group in `--mark` is written as "number=selector", separated by semicolons, and the numbers match the problem numbers in your message. Every element a group matches gets a box, and the number sits on the first one. A missing element is a hard error. Add `--full` for full-page problems, otherwise boxes below the first screen are not captured.

Actions in `--steps` are separated by semicolons. Quote selectors that contain spaces, for example `click ".nav .item"`. Without quotes it fails outright rather than silently clicking another element: `click selector`, `hover selector`, `drag selector dx dy`, `type selector text`, `key key`, `scroll dy`, `wait ms`.

Results go into the directory given by `--out`, `./shots` by default: one `<state>.png` per state, the text-masked version as `<state>-masked.png`, the marked version as `<state>-marked.png`, sheets as `sheet.png` and `sheet-masked.png`, and the recording as `record.mp4` plus `motion-start/mid/end.jpg`. Every image is checked for console errors, horizontal overflow, and images that failed to load. The last line of the command gives the verdict, and the details are in `report.json`. Recording needs ffmpeg installed on the machine. Without it only the three frames are kept.

Every screenshot is also checked for a set of problems that can be judged directly from page styles. The command output lists them under "Default-pattern hints", with details in the `lint` field of `report.json`:

- **Readability problems that must change**: text contrast below threshold (body under 4.5:1, large text under 3:1), body text under 13px, tight line height in multi-line body text, and first-screen content stuck transparent (entrance animation never fired?).
- **Change, or write down the reason**: gray text on a colored background, body line too long, and the model default patterns: eyebrow label above a heading, numbered label above a heading, colored single-side border, gradient text, nested cards, emoji as icons, English all-caps labels in a Chinese interface, and heading closer to the text above than below. For anything you keep, write in the delivery notes how it serves the direction.

The check produces false positives, for example genuine step numbers or labels that are really needed. Write a sentence about false positives in the delivery notes too. Text with contrast below 1.5:1 is usually a background the tool could not determine, and it is not reported, so look at those spots in the screenshot yourself. It only recognizes how things are written. It cannot judge whether they look good: once the hints are cleared, still look at the screenshots yourself.

`--compare` is for screenshot recreation: the reference image is scaled by width to the screenshot's width, and each screenshot gets a `<state>-compare.png` with four panels in order: reference, current, overlay, and difference heatmap. The heatmap marks pixels with a clear luminance difference in red and labels each cell of a 3×3 grid with its share of differing pixels. The command output gives the overall share and the three worst cells. First set `--size` to the reference image's logical size. For example, when the reference is a 2x image 2880 wide, use a width of 1440, otherwise you are comparing two misaligned images. Differences in text and image content also raise the number, so use it only to find which block to fix first and to see whether a change reduced the difference. It is not a recreation score.

`--motion` is only a floor check. Its result is in the `motion` field of `report.json`: no animation on first load, only continuous loops without an entrance, no feedback to the `--steps` action, or amplitude too small to see are all recorded as problems. For landing-type pages, no change at all while scrolling top to bottom is also a problem. It also reports how many layers change within 1.5 screens of first-screen scrolling and by how much, for reference only, not as a problem. Use it to verify pages that chose first-screen depth. It only says "whether it moved and how much". Whether it looks good still needs the recording and a review. Run it once before sending new interfaces and landing pages to review, and add the motion first if it reports problems. When the page itself cannot scroll (single-screen apps, mini-games), the tool skips the scroll check. When a scrollable app page gets this report, one line in the delivery notes saying it does not apply is enough. Animations inside Canvas and WebGL may not be detected. In that case the recording decides. Run `--motion` and `--record` separately, otherwise the recording inherits the scroll position left by the probe.

WebGL pages fall back to software rendering on machines without a GPU. When a canvas fails to create a drawing context, or the context is lost, the check records a problem: the screenshot still succeeds, but the picture is empty, and it cannot serve as evidence.

When the check reports errors unrelated to the screen, such as API 401 or 404 (for example a login endpoint in guest state), one line in the delivery notes is enough. Do not change login, API, or other business code to make the check pass.

Look at the result yourself before relying on it: whether the default state has finished loading, and whether the text-masked version has also covered graphics. Re-shoot wrong evidence before handing it to the reviewer.

## Style cards

```text
python3 <skill>/scripts/build_style_cards.py <config.json> --out <output directory> [--force]
```

Write the config following `assets/style-cards/example.json`, with 4–6 cards. The output directory holds each card's HTML, `manifest.json`, and `style-explorer.html`. Add `--force` to overwrite an existing comparison page. When to use them is in "Style cards" in [Design direction](design-direction.md).

## Writing interactive previews

A preview must open each state directly through a URL parameter, for example `?state=done`. The screenshot tool and the reviewer depend on it. Write one file per component or page. Do not copy a file per state.

Define colors, font sizes, spacing, and radii as a dozen or so CSS variables first, and reference the variables everywhere after that. Write one component's styles together using native CSS nesting. Do not bring in tools that need a build step, such as Tailwind or Sass.

Write states and interactions such as forms, toggles, and expansion in HTML attributes with Alpine.js. Do not hand-write a long script that toggles visibility. Put gesture tracking, physics simulation, Canvas and WebGL drawing, and audio in separate JS modules. Data that updates every frame does not go into Alpine's reactive state. Alpine only reads the module's results to update text and buttons. Use `$refs`, not `$el`, to find other regions from component methods: `$el` points at the element that triggered the event.

Adding Alpine.js:

1. Copy it into the task directory: `cp <skill>/assets/vendor/alpine.min.js <task directory>/vendor/`
2. Reference it in the page: `<script defer src="vendor/alpine.min.js"></script>`
3. Keep state in one `x-data`, and read the initial state from the URL parameter:

```html
<main x-data="{ state: new URLSearchParams(location.search).get('state') || 'idle', amount: 40 }">
  <p x-show="state === 'done'">Done</p>
  <input type="range" min="20" max="80" x-model.number="amount">
  <button @click="state = 'running'">Start</button>
</main>
```

When putting it on the comparison page, add `"interactive": true` to this candidate in the manifest. The generator inlines the CSS and JS files referenced from the task directory into the comparison page. No manual merging is needed.

In existing projects, use the project's own stack. Do not bring in Alpine.js.
