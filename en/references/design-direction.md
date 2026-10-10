# Design direction

## Contents

- [Name the category, break down a benchmark](#name-the-category-break-down-a-benchmark)
- [Set the tone first, then seek difference](#set-the-tone-first-then-seek-difference) (includes [translating vague words](#vague-words-must-be-translated))
- [Style cards](#style-cards)
- [Start a direction from a direction engine](#start-a-direction-from-a-direction-engine)
- [Decide the first-screen skeleton](#decide-the-first-screen-and-workspace-skeleton) ([persuasive skeletons](direction-persuasion.md))
- [Direction card](#direction-card)
- [Difference check](#difference-check)
- [North star and echoes](#north-star-and-echoes)
- [The memorable moment](#the-memorable-moment)
- [How references become design decisions](#how-references-become-design-decisions)
- [Previews, choice, and taste](#previews-choice-and-taste)

When nobody pushes it, the model gives the average answer that everyone can accept. "Make it more unique" and "make it more random" do not move it. It only swaps a few decorations. Every method here gives the model a concrete push: name the category and see how the best products in it work, then set the tone, start the direction from a direction engine, and finally force real difference with rules that can be checked. The goal of a direction is "the best team in this category would do it this way, and it has become this product's own look". Merely "different from the model's default" is not enough. A premium feel comes from the completeness and detail of one visual language, not from an unusual subject.

This file is mostly method. The occasional examples only show how concrete to get. They are not a style list. The subjects, materials, scenes, typefaces, and palettes in a direction are derived each time from the current product's content, audience, and setting. If a direction you think of collides with one of the common trendy styles, you must be able to name a reason that comes from this product. Otherwise choose again.

## Name the category, break down a benchmark

Before you start, name what category of product this is, then look at how the best products in that category do it. This step gives you the floor: the structure users are already used to, and the level of finish of first-rate products. The tone and the direction engine that follow look for this product's own thing on top of that floor.

Do it in three steps, and write each one down:

1. **Name the category and the benchmarks.** What category of product is this, for example "language learning app", "component library website", "project management tool", "portfolio gallery". Who are the two or three products in this category with the most distinctive style. Choose the most distinctive, not necessarily the most famous.
2. **Break one of them down.** Break it into 6–10 visible elements. For each, write two things: what it looks like, and why it is done that way. Break it down along these layers: the shape and feel of controls, typography, color, icons and illustration, states and feedback, motion, copy voice, what the first screen holds. Break it down until you could build from it. For example, a learning app is "chunky buttons that sink when pressed, with an exaggerated bounce on a correct answer", because answering is the core action and ordinary people using spare minutes need a tactile reward. A developer tool is "dark, tight line spacing, one consistent icon per state, shortcuts printed in the menus", because engineers spend hours a day inside it. If all you get is "clean, white space, one accent color", you have not broken it down far enough. Pick another product and break it down again.
3. **Decide what to keep and what to change.** Compare each item against this product's audience, content, and setting. If the reason still holds, keep it. If the reason does not hold, change it, and let the direction engine that follows supply the replacement. Write the result into the direction card under "Benchmark and trade-offs".

While breaking down, keep three things apart:

- **Baseline**: the structure users already expect, for example works come first in a gallery with filters at the top, and the cart sits top right in a store. Keep it so users do not have to relearn.
- **The category formula**: the default layout everyone in this category uses. At least one direction in a round must break it. See "Difference check".
- **A look-alike**: typeface, palette, key visual, and icons all match a benchmark with only the name changed. No direction is allowed to do this.

The test: take out a single button, a list row, an empty state, or one piece of feedback, drop it into another product, and you can still tell it belongs to this product. Recognition does not have to rely on shape and color. It can rely on density, typography, and the rhythm of motion. A black-and-white direction can pass this test too.

## Set the tone first, then seek difference

Derive the tone from the product's subject, audience, brand voice, and setting. Describe it on five scales, and write the evidence for each:

| Scale | Ends | What to look at on screen |
| --- | --- | --- |
| Energy | calm ↔ lively | Saturation, contrast, whether elements collide |
| Finish | raw ↔ polished | Edge treatment, grain and noise, how strict the alignment is |
| Density | airy ↔ dense | Scale of white space, layering, grid discipline |
| Weight | light ↔ heavy | Font weight, area of color blocks, hardness of shadows |
| Seriousness | playful ↔ formal | Corner radius, illustration language, size of motion |

For example "underground live-music community → lively, raw, dense", or "meditation companion → calm, polished, airy". Both are fully valid. What fails is a default with no evidence behind it:

- The evidence points to lively and raw, but what ships is beige cards, soft shadows, and generous white space. This is the most common failure: the design gets sanded back to the model's default "calm premium".
- The reverse: to look interesting, grain, torn-paper edges, and thick borders get forced onto a product that should be calm.

Once the evidence has locked the tone, keep every candidate inside that tone and open up the difference in composition, color identity, and key visual. Do not add a calm, minimal fallback "for balance". Only when the evidence is genuinely ambiguous should candidates spread across different tones.

### Vague words must be translated

"Premium, refined, restrained, epic, literary, clean" cannot serve as design reasons. When the user or you say a word like this, first translate it into observable decisions:

| Vague word | What it translates to |
| --- | --- |
| "Premium" | First say which kind of premium, then decide the contrast of the typeface, the way things are separated, the scale of spacing, and the number of hues. Saying "premium" alone decides nothing |
| "Refined" | Tolerances: how letter-spacing is tuned, which pixel grid things align to, how many levels of shadow at most, how many hues at most |
| "Restrained" | A saturation budget, for example the accent color covers no more than 10% of the screen. A ceiling on motion size. A ceiling on the number of hues |
| "Epic" | Scale: how large the display type is, how much area the key image takes, how strong the light-dark contrast is |
| "Literary" | The character of the type family, the line length, the line height, and the palette, with a value for each |
| "Rough" | Which techniques, and to what degree each, for example how many pixels of offset, how many degrees of rotation |
| "Clean" | A density setting, plus what gets deleted and why. Clean is a result, not an instruction |

A word that cannot be translated into an observable decision gets deleted from the reasoning.

Vague words about motion and interaction must likewise be translated into concrete patterns:

| Vague motion word | What it translates to |
| --- | --- |
| "Make it move when you scroll" | First decide whether it is scroll-triggered or scroll-driven. See "The two modes of scroll interaction" in [Scroll narrative](scroll-narrative.md). When unspecified, treat it as one-way and once-only |
| "Make page switching smoother" | Pick a transition mode: curtain, overlapping, or shared element. Trade-offs and durations are in "Stability trade-offs for full-page transitions" in [Motion](motion.md) |
| "Give the background some depth" | **Layered parallax displacement**: state the speed difference between background and foreground (for example background drifts at 0.2×, foreground at 1×), and body text must never get parallax |
| "The first screen needs impact" | State the single protagonist of the first screen (large type, one physical object, a core 3D piece, or video) and do not pile on secondary ornament. Entrance duration is in "Duration and amplitude" in [Motion](motion.md) |

## Style cards

Let the user pick a style from cards. Do not ask with adjectives.

- **Generate them with the script.** Write one config: one shared set of real text (title, body, one key number, primary and secondary buttons, tags, an input field). Each card then writes only its palette (background, surface, text, muted text, accent, text on accent, line, alert), typefaces (display, body, numbers, local font names only), corner radius, border, shadow, density, layout sketch, and one sentence describing the style. The layout sketch is chosen from 7 presets: for dashboards, sidebar and data table, top bar and card grid, queue and detail pane. For landing pages, centered heading and product preview, text and visual side by side, large type and columns, full-bleed visual with text overlay. Follow `assets/style-cards/example.json` for the format. It is an example for a different product and only shows how to fill the fields. The text, palette, typefaces, and styles are derived from the current product, not copied. Then run `python3 <skill>/scripts/build_style_cards.py <config> --out <folder under the task directory>`. It draws the cards and generates the comparison page.
- **What not to do.** Do not write separate pages, do not include real tables or full first screens, do not write interactions or motion, do not dispatch a review.
- **Difference.** 4–6 cards, one style each: palette, typefaces, control shape, density, and layout sketch change together, not just the main color. Draw from the benchmarks you broke down and from approaches that hold up in this category. Cover the major splits such as airy versus dense and cool versus warm. When the evidence has locked the tone, keep them all inside that tone and open up the difference in palette, typefaces, and controls. Leave out extreme styles almost nobody would pick. Text on the cards is written in the product interface's language.
- **Deliver.** Hand the user the local path of the generated `style-explorer.html`. Do not start a separate dev server. Each card's `concept` is one sentence about the style, and `traits` lists visible features, so the user can say "B's colors with D's density".
- **After the pick.** The card the user picked fixes the tone, palette, and typefaces. In the next round, produce 2–3 layout proposals, all in this card's style, differing in composition, key visual, and structure. Fold the user's change requests into them. Do not revise the cards on their own. Write the chosen style into the design notes. In the direction cards for the layout proposals, fill typography, color, and control grammar from this card.

## Start a direction from a direction engine

Every direction starts from a concrete engine, not from an adjective. Different directions should preferably use different engines:

- **Material × environment**: one material placed in one concrete environment, for example "wet clay × an afternoon studio". The material drives lighting, depth, edge treatment, and motion damping.
- **A concrete scene**: a scene with a time, a place, and light, for example "a convenience store at 2 a.m.". The scene's light, sound, materials, and rhythm drive color, texture, and motion speed. Suits emotional tools.
- **A character archetype**: give the product a personality, for example "a meticulous archivist", and let the personality decide typography, color, and movement.
- **A design movement or cultural grammar**: pick a design movement or visual tradition with a genuine connection to the product's subject, audience, or region. Borrow its grammar, not its patterns.
- **The complete expression of another field**: borrow the way another field's medium or object expresses itself, for example turning an itinerary into a boarding pass. Borrow only its one or two most recognizable techniques. The page stays in its original genre. Do not carry over that medium's parts one by one. That becomes a pile of props.
- **Historical media juxtaposed with frontier technology**: when the product belongs to the newest technology or an abstract concept (AI, algorithms, low-level infrastructure), borrow forms with historical weight or from traditional publishing (monochrome print, scientific survey manuscripts, academic journals, archival documents). The contrast gives intangible technology physical weight and avoids the industry's usual "dark background with glowing orbs" template.
- **Deliberately breaking convention**: radical asymmetric layouts, discordant palettes and typefaces, unsettling white space, while the whole still looks good and works completely.

Feeling words start from this brand, not from the industry. "Delicious, warm, appetizing" pushes every food app toward orange. "Late-night comfort, solitude, gentleness" belongs to one specific brand. The industry's customary colors may be used, provided the reason comes from this brand. If the reason is only "the whole industry does this", change it.

Before writing the direction card, flesh the direction out in your head: what it feels like to use, what surfaces and objects it brings to mind, how the page flows, which kind of person it is courting. The direction card is distilled from this thinking. Skip this step and the direction card is a thirty-word shell, and the page built afterwards will be flat too.

A random seed is also an engine: have a script generate a random string, and associate palette, layout, and typefaces from it. The seed does not enter the interface. It suits breaking out when you are stuck repeating yourself, but it is less explainable than the engines above.

## Decide the first-screen and workspace skeleton

Decide the skeleton before writing copy. The copy adapts to the skeleton. First answer one question: **what do users come to the first screen to see and do?**

- **Pages people come to for a line, a picture, or to be persuaded** (landing pages, brand pages, product launch pages, exhibition pages):
  pick from the 8 first-screen skeletons and leave the default split-layout template behind. See [First-screen skeletons for persuasive pages](direction-persuasion.md).
- **Pages people come to browse content, choose things, or handle objects** (galleries, stores, feeds, documentation, portfolios, tools, and dashboards):
  the first screen is the first row of content itself, or the workspace. Navigation, title, and filters together take no more than one or two lines, and the first row of content appears in full on the first screen. No first-screen slogan, and no paragraph explaining what this page is for. Arrange content around the action users perform most often. For browsing, let the content fill the screen. For handling, put the current object and the actions right next to each other.
- **When it is both** (for example a store homepage with a promotional banner on top): go with what users most often come to do. The banner may stay, but it must not push the first row of content off the first screen.

## Direction card

Write one direction card per direction. Fill every field with a concrete choice, not an adjective:

| Field | How far to take it |
| --- | --- |
| North star | One sentence of experience intent that can guide trade-offs: using it feels like being where, doing what |
| Tone | Values on the five scales, with evidence |
| Benchmark and trade-offs | What the category is, which product was broken down. Which items were kept and which changed, and why for each |
| Direction engine | Which kind was used, what it is specifically, and what evidence from this product it comes from |
| First-screen skeleton | First write what users come to the first screen to see. For content pages, how many objects the first screen shows and how many lines the header takes. For persuasive pages, which skeleton from the table was chosen, plus a 3–5 box first-screen wireframe: what each block is, how much area it takes, where reading starts |
| Page structure | How things are organized below the first screen, for example a single immersive scrolling column, or three panes for navigation, content, and detail |
| Form of each section | What each major section below the first screen (real product artifact, features, pricing, privacy, closing, and so on) becomes in this direction. The form is derived from the direction engine, not the same module in a different color |
| Typography | Specific type families, weights, and scale relationships: what display, body, and numbers each use, and how far apart they are |
| Color | The hex values used and their purposes. State this direction's color identity. Black, white, and gray plus one accent is also a complete answer |
| Key visual | Which image or graphic carries emotion and recognition, and whether it comes from reuse, generation, or the typography itself |
| Icons | Which set, what stroke weight and line caps, or no icons at all, using characters and numbering instead |
| Control grammar | The one set of shapes and feel shared by buttons, inputs, selection, tags, states, and motion, stated in one sentence, for example corner radius, stroke weight, and how things change when pressed |
| Motion | Write the feel as "action + physical object", for example "click: flipping a toggle switch". How each of the three basic motions moves and how they echo each other. For landing-type pages, also the scroll storyboard (section entrances, which scroll-driven narrative was chosen), see [Scroll narrative](scroll-narrative.md). Whether there is a clever touch found in the product. See [Motion](motion.md) |
| Structural break | The one departure from convention that changes the first-screen structure, and how it amplifies the north star. Local details such as handwritten annotations, textured buttons, and underlines do not count |
| Memorable moment | The one or two places where effort concentrates: at which moment or position, with what material, action, or drawing technique. See "The memorable moment" |
| What it gives up | The common practices this direction deliberately does not want |

North star, typography, palette, and traits go straight into the comparison page manifest and are shown alongside the screens.

## Difference check

Once the direction cards are written and before making previews, check item by item. When the user has already picked a style card, the proposals share the card's typography and palette, so the items about typography and color below do not apply. Skeleton, key visual, and page structure must still differ:

- **Compare wireframes, not descriptions**: put the first-screen wireframes of all directions side by side. The descriptions can all differ while the wireframes are all "big title on the left, small blocks on the right". Similar wireframes mean the same skeleton. Pick skeletons again.
- **At most one of the four may match**: of first-screen skeleton, typography, color, and key visual, any two directions may share at most one. Otherwise they are variants of one direction. Change the direction engine and rewrite one of them.
- **Do not split directions by light and dark**: the number one failure is "one light, one dark, one warm". Each direction needs its own color identity: a different hue family, a different sense of material, or plainly black and white. Light and dark are a result of color identity, not the basis for telling directions apart.
- **Black and white is also a color identity**: black, white, and gray plus one accent, or even no color at all, is a complete color identity. Color then goes to the content: product screenshots, the user's photos, a painting. It counts as opening up difference just as much as a multicolor scheme. The colors may be common or rare, as long as the reason comes from this product.
- **Structure must differ too**: different directions may organize the page differently. Three directions with identical page structure and only different colors and textures have not yet opened up difference. Candidates only need to share the core content and the main task.
- **At least one goes to an extreme**: within the tone range the evidence allows, at least one direction makes clear choices in composition, color, and key visual with no compromise. At most one direction is a compromise.
- **At least one breaks the category formula**: within the same tone, at least one direction does not use this category's default layout. Common formulas:
  Breaking the formula does not mean abandoning the baseline. The gallery still puts works first. Only the arrangement of works, the filters, and what opens on click may differ.
  - Dashboards: left sidebar, top bar plus card grid.
  - E-commerce: large banner, product grid plus footer.
  - Social: bottom tab bar, feed plus floating button.
  - Landing pages: key visual, features, testimonials, one final call to action.
  - Chat: contacts on the left, messages on the right.
  - AI and developer tools: black background, purple-blue glowing blurred halos, floating particles, and the ubiquitous pill buttons. Break it: try high-contrast monochrome print, glyphs distilled from a concrete metaphor, or hand over a real input command or a working workspace directly.
- **No look-alikes**: put each direction side by side with the benchmark it broke down. If typeface, palette, key visual, and icons all match with only the name changed, it is a look-alike. Redo it. Keeping the baseline is not a look-alike, for example a gallery putting works first.
- **Blind look**: cover the names and descriptions and look only at the screens. You can still say what different feeling each direction gives.

Once the previews exist, compare the real screens once more: look at the first screens side by side on the comparison page, squint, and see only the light and dark masses. If the masses are distributed alike, for example all one large block on the left and a small one on the right, go back to the skeleton table and redo it even when typefaces and colors differ. Do not patch it with decoration. Below the first screen, compare the whole page section by section.

## North star and echoes

Once the north star is chosen, turn it into a small number of mutually supporting relationships: the emptiness of the photography echoes the white space around the title. Narrow letterforms echo the vertical image. Low-saturation ambient color contrasts with the single action color. Each direction states its protagonist, its supporting cast, its repeated rhythm, and one structural break.

The break must change structure, for example the skeleton, proportions, or reading order of the first screen, not add one more decoration. It should strengthen the theme or guide the key action. When polishing, do not sand down the distinctive choices. When a new element does not reinforce the same intent, prefer leaving it out. Bold proposals must still be readable and usable.

## The memorable moment

Pages the model makes often pass everywhere and stick nowhere. Delight rarely comes from pushing the whole page. It comes from one place done to the limit: usually one action on one component, with the result, material, light and shadow, feel, and rhythm all in place. Each direction picks one or two places to concentrate effort and keeps everything else quiet.

Where to look:

- **Actions users perform.** Tapping, dragging, toggling, submitting become memorable more easily than scrolling.
- **Key moments.** Payment succeeded, the first completed task, an upgrade, a delete, an upload, waiting for a result. Emotion is strongest at these moments, and a small animation pays back the most.
- **Corner pages.** 404, empty states, loading, the footer. Nobody expects them, the risk is low, and they are the easiest place to shine.
- **While the AI is working.** Unfold the process in order: steps light up one by one, log lines stream in, a finished step collapses, the current step expands. Black text on white works just as well. No material or glow needed.

How to think:

- **Let the result happen on the spot.** A state change does not just swap an icon. The thing affected changes right there: turn on dark mode and the whole page dims like a blackout curtain coming down. Drag the time and the sky in the picture follows. The user sees the result, not a control performing.
- **Draw numbers as visible quantities.** Percentages, durations, balances: first ask whether they can be drawn as a quantity. Lit cells, a filled length, a grid where one cell is one day. The number is only a label. The quantity is the picture.
- **Give abstract states a material.** First ask "if this state were a physical object, what would it be", and find the answer in the product's own domain.
- **Deliver results through an object's action, and take the object from the user's own hands.** Pick what users in this domain already hold: a boarding pass works for a travel product. For a portfolio, a boarding pass is only a borrowed gag. Receipts, printers, cassettes, and old game consoles are already everywhere on inspiration sites. Before using one, ask: what is this product's own object.
- **Give controls physics and personality.** Dragging has elasticity and weight, pressing changes light and shadow, pulling too far snaps back reluctantly.
- **A drawing technique must have a traceable source.** Dot matrix, ASCII art, pixels, particles, photoreal materials: choose one only when you can say it comes from what the product does. A research tool that renders data as a dot matrix uses a dot matrix. A tool that lives in the terminal uses ASCII art. If you cannot name the source, do not choose it. Once chosen, carry it from the key visual all the way through loading, icons, and empty states.
- **When one picture is the base layer, the interface steps back.** An emotional photograph or painting fills the screen, the interface shrinks to one line of navigation and one sentence, and the typesetting is strict. The underlying image is blurred or darkened to keep the text readable.

## How references become design decisions

First state the purpose of the reference: borrowing visual relationships, establishing a quality baseline, or exact recreation. Describe its visuals only after actually looking at the image. When borrowing, extract relationships, for example "the title carries the main visual weight, the image supplies emotion, supporting information is pushed down in contrast", then reorganize with the current content. Do not copy the reference's business modules, logos, and copy. Metaphors are translated into interface decisions, not built as imitation shells that get in the way of use.

What the reference lacks is also a decision. If the reference's first screen has no title area and no explanatory paragraph, do not add them on its behalf. Do not add back decoration the reference did not use.

## Previews, choice, and taste

Pick the style with cards first. Layout proposals are only representative previews. Do not build several complete products from the start. Rounds and counts are in SKILL.md step 1.

Pick representative pages that expose each direction's strengths and weaknesses: a product with complex forms cannot show only a cover, and previews of long pages must include the key content structure.

A page that introduces a product must let users see what the product really delivers: a generated report, an exported contract, a piece of real processed data, instead of promising "what it can do" in words alone. This real artifact is often more persuasive than a feature list, and it most easily becomes the protagonist of one section below the first screen.

Reasons for a recommendation are weighed across task fit, recognizability, content capacity, readability, and implementation cost. When asking the user to add their taste, ask what feeling they want, what they do not want and why, and which parts to keep. When the user only says "a bit more premium", follow up with the translation table above, or hand them two previews to compare.

Write the chosen direction and the user's taste into the design notes as the baseline for later judgment. When a review proposes a new style, first judge whether it solves the original goal. Only when the current direction genuinely does not fit, or the user changes the goal, explore again.
