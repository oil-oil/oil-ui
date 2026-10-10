# Visual language

## Contents

- [From the whole to the parts](#from-the-whole-to-the-parts)
- [Focus and space](#focus-and-space)
- [Type and content](#type-and-content) (including [Readability is a delivery bar](#readability-is-a-delivery-bar))
- [Color and surfaces](#color-and-surfaces)
- [Controls and icons](#controls-and-icons)

## From the whole to the parts

Look at the information focus, the composition, and the content density first, then adjust space, typography, color, and details. When an earlier layer has already solved the problem, do not keep adding styles to look polished.

Use the project's working design tokens, components, and reference relationships. Where there is no standard, define only the text, color, and spacing roles needed now. Do not generate a complete design system out of thin air.

Every change should be explainable: which visible element, which relationship has a problem, what is adjusted, and what improvement is expected. A source-code check can prove that styles are inconsistent. It cannot on its own prove the screen looks better.

## Focus and space

- Every task area has a recognizable primary piece of information or primary action. Supporting information recedes through scale, weight, contrast, or position. Do not let several strong emphases compete for attention at once.
- Relationships of the same kind keep the same spacing. Tighter within a group, looser between groups. Build structure with alignment and white space first, then decide whether a container or divider is needed.
- White space does grouping, focus, or rhythm. Tool interfaces do not sacrifice necessary information for emptiness, and brand pages are not forced to fill the first screen.
- Asymmetry, shapes that cross boundaries, or large-scale type can express the chosen direction, but they need stable local alignment and a clear reading order. Do not treat deliberate asymmetry as an error by default.
- The parent layout arranges regions. A component owns its own internal space. The same distance should not be added twice by several layers of styles.
- Put content directly on the canvas first and organize it with alignment, font size, and white space. Containers appear only where there is real grouping, selection, background contrast, or an operation boundary. Do not wrap the page, the module, the item, and the item's description in card after card.
- Dividers and borders must not repeat. Each line does one job: no double line at the same separation, no single line plus a box, no line where white space already separates, and no lines redrawn at every level. Line weight follows hierarchy, for example a thick line divides the page and a thin line divides columns, consistently across the page. When lines are part of the style, keep them. Delete only the duplicates.

## Type and content

- Build text roles for headings, body, supporting information, labels, and data. Roles stay stable, and levels differ enough. Actual content length decides wrapping and space.
- Check the target language's glyphs, weights, and fallback fonts. A good-looking English sample does not prove the Chinese layout works. In mixed Chinese and Latin text, check baselines and visual weight.
- Body line length and line height serve reading. Dense tables are arranged for scanning and comparison, not article typography. Numbers compared vertically can use tabular figures.
- Important names and descriptions are not clipped by fixed heights. When truncation is truly needed, keep an accessible way to the full content, and make sure similar names stay distinguishable after truncation.
- Write the actual product content first, then tune the layout. Buttons state the outcome of the action. Value statements use real uses, not empty slogans, fabricated endorsements, or meaningless English filling the layout.

### Readability is a delivery bar

Judge font size and line height in the real viewport, with the actual fonts, at 100% reading size. Thumbnails can only judge composition. Chinese body text on reading pages usually starts at 16–18px, product interface body text at 14–16px, and dense tools used for hours every day can go to 13–14px. Body unitless line height is 1.6–1.75. Action text is usually 14–16px. These are starting points, not fixed rules across products. Do not manufacture "refinement" with 9–12px captions, low-contrast thin text, or compressed line heights. When there is too much information, cut redundancy, adjust hierarchy, or rearrange first.

Multi-line Chinese headings usually start at a line height of 1.2–1.35, checked against the real glyphs. Do not copy the extremely tight line heights of English all-caps posters, do not fix heading height to a single line, and do not squeeze following content with negative margins. When display type truly needs to be tighter, you must have seen the actual wrapping in every supported viewport and confirmed that glyphs do not collide.

Control Chinese line breaking actively: `text-wrap: pretty` or `balance` can only reduce orphans, not eliminate them. Wrap numbers with their units (38 seconds, 47 minutes) and short unbreakable words in no-wrap. Break short passages such as first-screen descriptions and margin notes by hand according to meaning. One or two characters left at the end of a line, or a word split across two lines, both count as defects.

**Condensed display type (Condensed / Compressed)**: at large sizes (80px and above), condensed gothic sans-serifs bring a strong slogan feel and typographic tension, and fit more characters on one line. But they sacrifice horizontal legibility and suit only display headings and very short numbered labels. Body text and long reading should use fonts of regular width.

At acceptance, look at long headings, two to three lines of body text, mixed Chinese and Latin text, numbers with units, and font fallback. On narrow screens and after zooming in, check line spacing, the sections above and below, and the inside of buttons. Overlapping text, truncated key information, or text pressed by a neighboring region counts as unfinished. Fix line height, content-driven height, and container flexing first, and only then consider a smaller font size.

### Sample data must look real

Sample data exposes the template feel, even when the visual layer is already good. Avoid: round-number metrics (1,000 users, +10%), John Doe and Example Inc., every item "2 hours ago", placeholders reading "Title" and "Description", and "Learn more" and "Get started" repeated across the page. Real data is uneven: 1,238 users, +1.83%, times like "just now", "yesterday 16:12", "March 14". Names are long and short, which also tests the layout of long names. Buttons name the specific action, such as "Save draft" or "Send Tuesday". When one page carries many demos (a component catalog, a template library, a feature showcase), let them share one concrete fictional scenario: the same product, the same people, the same files and numbers, so the demos echo one another. That is far more believable than each making up its own "Sample title". Do not use library names or the tech stack as demo content.

## Color and surfaces

Use color by meaning: text, background, action, selection, and state. Brand color and semantic states can coexist, but important states must not be distinguished by color alone.

Borders, shadows, materials, and gradients must agree with the direction and help with layering, atmosphere, or brand recognition. Do not ban purple, rounded corners, or gradients outright. The problem is meaningless repetition, confused hierarchy, and unsuitability for the task.

Avoid giving every ordinary card a different accent color, a heavy border, and a heavy shadow. The same level keeps the same weight. Nested inner outlines coordinate with the outer container.

Run two self-checks on the palette: does it still hold with every glow and blur removed, and can you name a successful product or publication with a similar palette? Surface levels can be distinguished by shifts in color temperature and hue, not only by light and dark. After choosing the palette, ask one more question: was this set of colors derived from this product's content, users, or brand, or is it a safe set that would not look wrong on any product? If the latter, go back to the product and look again.

Take texture from the tone's finish, and do not mix the two ends:
- The polished end: surface highlights, soft layered shadows, subtle warm-cool cross tints, hairline dividers.
- The raw end: marks left by hand and by printing, found in this direction's engine, not a fixed set of props.

**Monochrome and duotone systems (Duotone Print)**: besides several levels of neutral gray plus one accent, try a purely monochrome or duotone system. The whole page is built from a single primary color and a single paper color. Secondary information, borders, and disabled states all derive from the primary through transparency or blending with the paper color. This restraint brings the purity and high recognizability of a single-color screen print.

**Alternating inverted blocks**: the sections of a long page can try a technique like a print negative, cutting with hard edges between light text on a dark ground and dark text on a light ground, without soft gradient transitions, producing clear paragraph stops and rhythm.

Check that text, control boundaries, focus, and selected states are recognizable on the actual background, especially on images, transparency, and moving backgrounds. Follow the project's existing accessibility targets. Basic reading and operation must not depend on guessing.

## Controls and icons

Keep one icon language, optical size, and text alignment across an interface. Prefer mature resources for common icons. Make special brand illustrations separately, and do not add an icon to every heading mechanically.

Clickable elements need a recognizable entry and matching feedback. Default, pressed, focused, selected, disabled, and processing express different meanings. Mouse hover cannot replace touch and keyboard entry. Feedback changes keep the click area and the neighboring layout stable.

Controls are a grammar: radius, stroke, weight, shadow, displacement when pressed, the expression of selection, and state icons follow one logic across buttons, inputs, labels, switches, and empty states. The direction runs through the page and through every control. When buttons and inputs still look like the component library's defaults and nobody could name the product after a primary-color swap, the controls have not entered the direction yet.

Unfamiliar icons get visible text. Icon-only buttons still need an accessible name. Arrow symbols carry meaning: ↗ means opening a new page or an external link, and in-place actions such as submit and check do not use it. Static labels and decoration must not pose as buttons, and inline buttons must not trigger the enclosing card's action by accident.

### Icon libraries converge too

The model's default is Lucide or Heroicons: 24px, 2px stroke, round caps. The library itself is fine. The problem is that every direction uses the same set in the same way. Icons, like type, are part of the direction. Write in the direction card which set, what weight, and what caps, or no icons at all.

| The direction's character | Consider | Traits |
| --- | --- | --- |
| Refined, editorial, luxury | Phosphor Thin or Light, Iconoir | Thin strokes, paired with light-weight serifs or sans-serifs |
| Industrial, instruments, enterprise tools | Carbon, Material Symbols Sharp, Radix Icons | Square caps, strict grid. Radix is designed for compact 15px interfaces |
| Friendly, rounded, consumer | Phosphor Fill or Duotone, MingCute | Round caps, filled or two-tone |
| Chinese products that need many business icons | IconPark, Remix Icon | Broad coverage. IconPark can adjust stroke weight, caps, and theme |
| Continuously adjustable weight and fill | Material Symbols | Variable font. Fill, weight, and optical size all adjust continuously |
| Pixel, games, retro | Pixelarticons | Pixel grid |
| Brand logos | Simple Icons | Vector shapes of brand logos |

Iconify can fetch single SVGs from most of the libraries above by name.

- **One set per product.** When filling gaps, pick icons with matching stroke, caps, and radius, and normalize them to the same canvas size and stroke width.
- **Weight follows the type weight.** Icon strokes approach the stroke thickness of body text at the same size: 1–1.5px with light type, 2px or more or filled with bold type. Icon size is about 1–1.25 times the font size, aligned to the text by optical center, not by bounding box.
- **Skip icons where you can.** Editorial directions often use characters themselves: → ↗ ※ §, numbers, abbreviations. Use icons only where they speed up recognition.
- **Hand-draw the brand moments.** In a few places such as the core action and empty states, draw bespoke line icons or small illustrations in the direction's own line language. Common actions still use the library. Key visuals such as characters, props, and scenes are not hand-drawn SVG. See [Assets](media.md).
- **Inline in previews.** Self-contained previews inline only the SVGs they use, without icon fonts or CDNs. Existing projects keep their current library. Switching libraries is a redesign.
- **Check the license.** Most are MIT, Apache, or ISC. SF Symbols may be used only in interfaces on Apple platforms, not on the web. Libraries that require attribution get it as required.
