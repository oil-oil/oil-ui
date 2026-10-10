# Motion

## Three motions first in every interface

An interface that never moves looks like a screenshot: a press gets no response, a switch has no origin, and the user can only guess what just happened. For a new interface, or one whose operation flow changed, build these three motions first. Write the feel into the "Motion" row of the direction card. When changing a flow or adding a feature, write it into the proposal card or the design notes:

1. **Primary-action feedback.** The press answers at once and hands over a result on completion: the button sinks and springs back, the check mark draws itself, the number rolls to its new value.
2. **Where one state change comes from.** When something is selected, expanded, switched to another view, or added to or removed from a list, let people see where it came from and where it went. See "Interface transitions" below.
3. **One entrance on first load.** The protagonist arrives first, the rest follow in reading order. Plays only on first load.

Before adding motion beyond these three, ask: if it took a week to hand-write, would it still be worth doing? The model makes motion free, and scroll fade-ins, parallax, cursor-following, and decorative loops are the first to become noise. Every motion must carry one of these jobs: feedback, guidance, continuity, or brand expression.

| Purpose | Approaches worth considering |
| --- | --- |
| Press, focus, expand, or an ordinary state change | Native capabilities or a small transition on an existing component |
| Switching between views, elements changing position | Shared-element transitions, see "Interface transitions" below |
| Drag, gestures, spatial change, and complex choreography | The project's existing mature motion capabilities |
| Special brand scenes, materials, complex physics | Images, 3D, shaders, or pre-rendered video, chosen per need. When to use real-time 3D is in [Assets](media.md) |
| Mouse, touch, or scroll controlling narrative progress | Map the input to an explicit animation progress and handle reversal and fast input. The approach is in "Scroll narrative" below |

Code animation suits interfaces that need precise state control. Generated video suits visual changes that are fixed in advance. Video cannot replace controls that need live data and real operation.

## Feel

The feel of a motion is derived from the direction's material and tone. Name it and choose its parameters (spring stiffness / damping) as "action + physical object":

| Action | Physical reference | Stiffness / damping | Suits |
| --- | --- | --- | --- |
| Click | Magnet snapping, latch, toggle switch | 350–400 / 10–15 | Buttons, switches, dropdown expand |
| Glide | Pneumatic door closer, drawer damper | 250–300 / 20–25 | Bottom panels, drawers, folding |
| Pour | Pouring honey, mist spreading | 150–200 / 30–40 | Page transitions, key visual appearing |
| Slam | Hammer blow, heavy object landing on a table | 400–500 / 5–10 | Confirming a choice, completion feedback |
| Bounce | Rubber ball, trampoline | 300 / 8 | Celebration prompts, children's and game products |
| Float | Helium balloon, drifting fluff | 100 / 25 | Meditation, dreamlike scenes, idle loops |

Heavy materials (stone, metal, ceramic) lean toward click and slam. Light materials (paper, cloth, mist) lean toward float and pour. High-frequency operations use short actions. Only rare brand moments use long ones. A lively, raw direction may use hard cuts, 80–150ms linear jumps, and dropped frames as deliberate brand expression. What is forbidden is only the default easing nobody thought about.

Overshoot scales with area. Large things, a whole page or a panel, overshoot no more than 1–2%, or the whole surface wobbles. Small things, badges and check marks, may overshoot 10–20% and read as springy. The low-damping parameters in the table are for small objects only.

On the web a spring can be written as an easing curve: integrate the displacement numerically from stiffness and damping, take 20–30 sample points, and write them into `linear()`. The duration is the moment the displacement settles within 0.5% of its endpoint. Browsers without support fall back to a close `cubic-bezier`.

## Echo: make actions connect

Stiff motion moves each thing on its own: the button flashes by itself, the panel slides out by itself, the number is simply replaced. Good motion reads like a sentence: the change one action causes travels along a single path, and the end of one segment is the start of the next.

- **Start from the thing that was operated.** Tap "Add to bag" and the product shrinks to a dot that flies into the bag, and the count on the bag jumps. Delete a row and it collapses toward the delete button while the rows below move up to fill.
- **One switch, one direction.** When the card slides left, the title, index, and background color change leftward too. When the number rolls up, the progress rises too. Once directions scatter, you have several unrelated animations.
- **The protagonist moves first, the rest are carried along.** Affected things follow 40–80ms later with a smaller amplitude, as if pulled by the protagonist. Everything starting at once with the same amplitude just looks like a flash.
- **Shape handoff.** An element in the previous state becomes an element in the next: the button expands into the panel, the search icon stretches into the input, the play button becomes the pause button. The user sees at a glance that they are the same thing.
- **The movement and the picture are the same material.** A paper direction switches lightly with a slight pause. A hardware direction has switches that click into place. A liquid or glass direction uses pouring and refraction.

### A clever touch comes from the product

A clever touch is one motion that tells this product's own story. It is not more flourish. Find one action in the content that only this product has:

- A weather app switches to rain and drops land on the card. After the rain stops, the water marks on the card slowly dry.
- An expense app records a purchase and the slice taken from the budget bar falls into that entry.
- A music player changes tracks and the new cover's color spreads from the center of the record across the whole background.
- Completing a to-do draws the check mark with the same stroke as the brand logo.

If no such action exists, get the three basic motions right and do not force one. One or two clever touches per page at most. The remaining motion stays quiet and brief.

## Interface transitions

**Continuity.** What the user tapped is the protagonist of the next screen. Going from a list to a detail view, the tapped item grows into the detail and the other items fade out. On return it shrinks back into place and the page returns to its previous scroll position. If the original position is no longer in the viewport, scroll it into view first, then shrink back.

**Consistent direction.** The next item enters from the right, the previous from the left. Open and close are inverses of each other. A side panel slides in and out on the side it lives on. Animation with arbitrary direction confuses more than no animation.

**No cross-fade when only the shape changes.** Switching viewport, filtering, expanding a description, zooming: in these changes the content is still the same thing, only its size and position changed. Let the frame morph directly and show the new state of the content immediately. A cross-fade stacks two differently scaled pictures and produces ghosting. Fade only when the content itself was replaced.

**Handle leaving, joining, and staying separately.** Removed items fade out, new items fade in, remaining items slide to their new positions. Use the same fade for all three and the whole list flickers.

**Selection indicators use one moving slider.** Segmented controls, tabs, and the current list item all use one backing plate that slides to its new position, instead of the old one going dark and the new one lighting up. When options differ in width, transition the width too. On first display, window resize, and after fonts load, place it directly. Do not grow it from zero width.

**Prepare the destination first.** Content the destination has to load, such as images or embedded pages, is loaded or pre-rendered beforehand, or the animation stalls on a blank patch. Views that are switched back and forth are pre-rendered and stay in the page. Switching only moves them, nothing reloads. Fade in after content has loaded. Do not flash a white background first.

**Leaving is faster than entering.** Exit duration is about 60–70% of entry, on an accelerating curve. Entry uses a decelerating curve or a spring.

**The end gives feedback.** On the first or last item, nudge gently (10–15px out and back) instead of giving no response.

### Stability trade-offs for full-page transitions

A full-page switch differs from a component transition. It involves the handover of routes and DOM lifecycles. By stability and complexity there are three kinds:

- **Curtain / wipe.** A solid color, texture, or geometric mask sweeps across or covers the screen completely, and the new page mounts and the old one unmounts behind it. The simplest and most stable. It fully decouples the two page structures and suits the vast majority of ordinary and complex pages.
- **Overlapping.** The two pages interleave, push, or fade in layers within the same screen. Visually continuous, but it needs two DOM layers to exist at once and has to manage stacking and memory.
- **Shared element.** One key visual element (a thumbnail growing into the detail hero, for example) morphs across the page boundary. The smoothest visually, and the most fragile: a fast double tap, an interrupted navigation, going back, or a viewport change easily misaligns it and produces flicker bugs. It must have a fallback that places things directly.

A first-visit loading screen (splash) may reserve a short narrative or progress display for heavy assets. In-site page navigation follows the full-page values in "Duration and amplitude" below. A transition never stands between the user and the information.

## Duration and amplitude

| Object | Duration | Notes |
| --- | --- | --- |
| Press, switch, selection indicator | 150–300ms | Press scales to 0.96–0.98, takes effect immediately on press (about 80ms), springs back on release |
| Dropdown, popover, tooltip | 180–250ms | Expands from the direction of the trigger, scale starts around 0.96, not from 0 |
| Panel, drawer, sidebar | 250–400ms | Set by travel distance, the farther the longer |
| Full page or view switch | 350–500ms | Past 500ms people wait |
| Items appearing in sequence on first load | 40–80ms between items | Total no more than 600ms. Plays only on first load, not on re-render or state restore |

This table governs interface operations. Performance durations for games and lotteries are in [Play](play.md).

Hover lifts 2–4px with the shadow deepening to match. A hover effect that moves more than 20px looks flighty.

## Say the invisible result out loud

When a tap causes an invisible side effect, such as copying to the clipboard, saving in the background, or sending, use a brief notice that states the result itself, for example "Copied: …", rather than only "Success". Confirming moments, such as selection or completion, may use one small pop that plays only on the first state change. Repeated taps do not replay it.

## Scroll narrative

Landing pages, brand pages, launch pages, and exhibition pages must, beyond the three basic motions, build scroll motion per [Scroll narrative](scroll-narrative.md): sections enter by content, plus at least one scroll-driven narrative (first-screen depth, one continuous shot, and so on, chosen per page), implemented with a mature motion library. Documents, articles, tools, and dashboards do not.

## Experience and performance

Follow the project's motion rhythm and component capabilities. Feedback for high-frequency operations is immediate. Animation never delays the business result.

Animation must be interruptible. Under fast repeated operation, the new animation continues from the current position instead of jumping back to the start and replaying. CSS transitions restart from the current value and suit high-frequency switching. Keyframe animations replay from the beginning and suit one-off entrances. Business state updates immediately, not after the animation ends.

Continuous web animation prefers transform and opacity, declaring only the properties that change. Small indicator blocks may transition width and height directly. Frame-by-frame work needs stop and cleanup conditions. Avoid frequent interleaved layout reads and writes. Stop playback when off-screen or idle. The page usually ignores clicks during a full-page transition, so full-page transitions must be short.

Noticeable displacement, scaling, and scroll effects need an equivalent presentation under "reduced motion", where every state is placed directly. Essential information and primary actions never depend on autoplay, sound, or an animation running to completion.

## Checking motion

Static screenshots prove nothing about motion. The three basic motions and the memorable motion moment each need evidence: a 3–5 second screen recording, or start, middle, and end frames, with the triggering action written down. Set playback speed to 10%, using the browser devtools animation panel or the animation speed in an automation tool, and screenshot the transition halfway through. Look for ghosting, jumps, elements appearing suddenly, or flying in from odd positions. Check start, middle, end, and reverse one by one. Then tap rapidly several times and confirm nothing gets stuck in an intermediate state. Finally turn on "reduced motion" and walk through again. Report frame rate or performance improvements only after actually measuring them.

## Web implementation notes

- The browser's native view transitions suit "the same object changing from one place to another": give the elements that represent the same object in the two states the same transition name. A name must be unique at any one moment.
- In a shape-only transition, hide the old snapshot and show the new state directly, and there is no ghosting.
- Only a few pseudo-classes may follow the transition pseudo-elements, for example `:only-child`. Writing `:not(...)` invalidates the whole rule. To vary rules by scenario, toggle an attribute on the root element.
- Embedded pages and images are captured as snapshots during a transition. If the transition starts before the destination has loaded, it ends on a blank.
