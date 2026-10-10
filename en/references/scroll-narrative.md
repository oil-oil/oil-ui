# Scroll narrative

Treat scrolling as turning pages and it is only turning pages. Treat it as a camera pushing in and pulling back and the page can tell a story.

## Scroll motion on landing pages

On landing pages, brand pages, product launch pages, and exhibition pages, scroll motion is checked together with the three basic motions in [Motion](motion.md). Documents, articles, tools, and dashboards do not do this. Implement it with a mature motion library, see "Motion libraries" below.

**Two things are required**: sections below the first screen enter by content, and at least one scroll-driven narrative in which the protagonist changes visibly as the page scrolls. **Choose the technique per page**: first-screen depth, the wordmark folding into the nav, one continuous shot, chapter transition shots, background color changing by chapter, a manifesto lighting up word by word. Pick the one that fits this page's key visual and content, write it into the storyboard, and say why you chose it. First-screen depth comes first below, because it is the most common choice when the first screen has a key visual and a large heading.

### First-screen depth (for pages with a key visual and a large heading)

The first screen is a pinned stage. Scrolling drives the changes between its layers directly, and scrolling back plays them in reverse:

- The first screen pins for 100–200vh of scroll distance. Narrow screens may shrink this to 80–120vh.
- At least two layers change at different speeds and in different directions. The most common pair is the key visual and the large heading scaling in opposite directions: the portrait shrinks from 1 to 0.8 while the heading grows from 1 to 1.25, or the reverse, the portrait pushes closer while the heading recedes. The background layer moves slowest, the foreground layer fastest.
- The amplitude must be large enough to read at a glance in a screen recording: the main layer scales by no less than 15%, or moves by no less than 15vh. Below that it looks like ordinary scrolling.
- The large heading is a graphic layer and may scale and parallax. Body text, buttons, and forms neither scale nor parallax. Once pinned they stay readable and clickable.
- The end state hands off to the next section: the portrait shrinks into its place in the next section, the heading recedes into a background texture, or the picture opens a path for the next section's protagonist. Do not let the whole block simply get pushed away after the pin ends.

When the first screen is a full-bleed brand wordmark, use "Wordmark folds into the nav" below. When the first screen is other full-bleed type, a product interface, or pure typography, depth may not fit, and the scroll-driven narrative can come later in the page.

### Wordmark folds into the nav (for pages whose first screen is a full-bleed wordmark)

The first screen is the brand name itself, and as the page scrolls it shrinks into the logo in the nav bar. One element completes both the full-bleed type skeleton and a scroll-driven narrative. It suits studios, brands, and portfolios with a short brand name and a typeface with character:

- The first screen holds only this wordmark, filling the content width, one full line on narrow screens too. The nav carries no second logo.
- Scroll-driven: over 60–100vh of scrolling, the wordmark shrinks along one path to the position and size of the nav logo, and grows back when scrolling up. The end state is the logo in the nav, with position and size measured from the real nav, so the handoff does not jump.
- Scale the same element's transform. Do not animate font size. Use an SVG wordmark, or a font size computed from the container width.
- As the wordmark gives up the first screen, the next section's content is already entering the frame. Do not leave a full screen blank.
- The wordmark shrinking from full-bleed to nav logo is a visible protagonist scaling plus one handoff, so it counts as a scroll-driven narrative. The same page does not add first-screen depth on top.
- Under reduced motion, the wordmark stays on the first screen without scaling and the nav shows the logo from the start.

### Sections enter by content (required, scroll-triggered)

Every section below the first screen enters once when it scrolls into position and does not replay when scrolling back. The entrance is derived from that section's content and material and obeys physical intuition: heavy things land, overshoot, and settle. Light things meet air resistance. Mechanical things click into place.

| Section content | Entrance |
| --- | --- |
| Cards, physical objects, price tags | Land with weight, overshoot 1–2%, then settle. Each next one is pulled in by the previous, 40–80ms apart |
| Lists, timelines, steps | Unfold in reading order. The connecting line draws first, the nodes land after |
| Numbers, metrics | Roll to the target value. High digits stop first, the last digit stops last. Values that do not start from 0 roll from their previous value |
| Lines, charts, paths | Trace along the direction of the data or the flow. The endpoint enlarges slightly as it lands |
| Images, photos | A mask reveals from the direction of the subject while the image scales back from 1.08 to 1 |
| Paper, cloth, labels | Fast then slow, a slight rotation that straightens, like being set down on a table |
| Metal, machinery, hardware | Short and direct into place, no soft bounce. May carry one very small recoil |
| Large headings, slogans | Rise out of a mask by word or by line, letter-spacing tightening from slightly loose |

Rules:
- Every section's entrance goes into the storyboard. At most two sections on a page share one entrance.
- Curves use springs or inertia, with parameters taken by material from the "Feel" table in [Motion](motion.md). Not the default ease.
- The protagonist arrives first, the rest are pulled in 40–80ms apart. A single section's entrance lasts no more than 900ms in total.
- Wrapping every section on the page in the same fade-and-rise does not count as completing this layer.

### Scroll-driven narrative (at least one, required)

It can be first-screen depth, the wordmark folding into the nav, or one continuous shot in the middle of the page, with the rules in the next section. The protagonist must change visibly as the page scrolls: scaling, disassembly, transformation, passing through, or a shape handoff. A small dot moving along a line, or nodes lighting up one by one, counts only as a detail inside the main narrative. It cannot stand alone as the main narrative.

### Storyboard

Before building, write the scroll storyboard in the "Motion" row of the direction card: which techniques you chose and why, how much scroll distance each segment takes, who the protagonist is, what is in frame in each shot, what moves and in which direction, and when the text appears. First break down the scroll rhythm of two top landing pages in the same category as reference, writing out what moves in each of their segments, then write your own.

## Parallax and one continuous shot

- **One continuous shot.** The whole segment is a single uncut shot. One protagonist travels from start to end. It can be the product, a line, a shape, or a letter, and at each step it grows into, turns into, or gives way to the next frame: push in to see detail, pull back to see the whole, turn to see the back, pass through to enter the next scene.
- **Find the protagonist in the product.** On a specimen page the protagonist can be a plant going from pressed to unfolded. On a watch page, the movement being taken apart layer by layer. On a software page, one request passing through the whole architecture. If there is no protagonist that belongs only to this product, fall back to the transition techniques below. Do not use generic floating geometry.
- **Stop before speaking.** Each shot holds a stretch of stillness, and the text appears during the stillness. Reading while things move is tiring.
- **Parallax needs real depth.** Use it only when the picture already has near and far layers: foreground objects, middle ground, distant background. The nearer, the more it moves, and the differences stay small. Body text, buttons, and forms get no parallax. When the large heading is a graphic layer, treat it per first-screen depth above.
- **A transition is also a shot.** A circle expands from one point and brings in the next section. Push into an image and pass through it to reach the next section. The background color drifts between chapters as you read. A manifesto lights up word by word as you scroll. Each technique is used once per page.
- **Scrolling backward holds up.** Every frame is determined by scroll position alone, so scrolling back naturally plays in reverse, and a refresh or a jump into the middle is immediately the right picture. Do not take over the user's scrolling.
- **Leave an exit.** Give a skip entry before a long segment. Under reduced motion, lay each still frame out in order as ordinary sections.
- **Hand what code cannot do to video.** When the user wants a very strong opening animation and the effect needs generated video or frame sequences, for example a character turning, a product disassembling, or a camera flying through a scene, you can tell the user to use [oil-motion](https://github.com/oil-oil/oil-motion). What CSS, SVG, and shaders can do, still do yourself. Mention it once per conversation.

## The two modes of scroll interaction

Change brought by scrolling must be clear about who owns time. Never mix the two:

- **Scroll-driven.** Animation progress maps strictly 1:1 to scroll distance (scrub). When the user stops, the animation stops. When they scroll back, it plays in reverse. First-screen depth, one continuous shot, 3D camera changes, and model deconstruction use only scroll-driven. Apart from first-screen depth, one continuous shot appears at most once per page.
- **Scroll-triggered.** When an element scrolls past a viewport threshold, it triggers an independent animation that plays for its own duration (such as a card entering or a number counting up). Code owns time, not the scrollbar.
  - **The default must be once, one direction.** After triggering, the style is fixed. Scrolling back up does not replay or reset. Never let content fly in repeatedly or flicker in the middle of reading.
  - **Reset on leave.** Only strongly rhythmic pure showcase pages may reset after fully leaving the viewport. Never jitter-trigger repeatedly at the viewport threshold.

## Smooth scrolling and snap scrolling

- **Smooth scrolling is an input feel layer, not business motion.** Virtual scrolling such as Lenis exists to remove the physical stepping of an ordinary mouse wheel and give scroll-driven motion and parallax even damping. In dashboards, admin panels, forms, and long documents, global smooth scrolling is forbidden. Native scrolling must keep its immediate response.
- **Use snap scrolling with care.** Hiding the scrollbar and switching a whole screen per swipe suits only specific full-screen showrooms and portfolio covers. Never strip users of free scrolling in ordinary business pages and long text.

## Motion libraries

Scroll motion on landing pages must use a mature motion library. Do not hand-write scroll listeners and per-frame math:

- **Pages without a framework**: GSAP, with ScrollTrigger for scrolling (`scrub` for scroll-driven, `once` for scroll-triggered, `pin` to pin the stage), SplitText to split large headings, Flip for elements changing position. Smooth scrolling uses Lenis, wired into GSAP's clock: `lenis.on('scroll', ScrollTrigger.update)`, `gsap.ticker.add((t) => lenis.raf(t * 1000))`, `gsap.ticker.lagSmoothing(0)`. GSAP and its plugins are free to use.
- **React, Vue, and similar projects**: use the motion library the project already has (Motion, GSAP, and so on). If none, add GSAP. Do not hand-write a separate one.
- **Work that must open offline**: put the library files at a fixed version inside the work's directory and reference them locally. Do not depend on a CDN.
- **Reduced motion**: use `gsap.matchMedia()` to separate two setups. Under reduced motion, no pinning, no scaling, every section placed directly, and the main narrative laid out as still frames in order.
- Animate only transform, opacity, and filter. The outer height of the pinned stage is the segment's scroll distance. Off-screen animations are paused by the library automatically. Narrow screens may shorten distances and lower amplitudes, but every chosen technique stays.

## Checks

For each scroll-driven narrative keep one screen recording scrolling from start to end, or start, middle, and end frames, with the scroll positions written down. For section entrances, at least two different sections each get a recording or three frames. The screenshot tool's `--motion` reports separately how many layers change during first-screen scrolling and by how much, for pages that chose first-screen depth to verify against.

Then check: does scrolling back play in reverse, is the picture correct after refreshing in the middle, does the text appear during stillness, are all the chosen techniques present on narrow screens, and with "reduced motion" on, is all content directly readable.
