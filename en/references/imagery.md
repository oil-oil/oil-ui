# Imagery

The most common failure of a generated image is not poor drawing. It is drawing too much. The richer the detail, the more it looks like a stock photo. Dropped into a layout, it has no focal point and no relationship to the page. A good image carries meaning first, then mood, and finally joins the page as one whole.

Most of this file is about imagery for web pages. For the characters, props, collectibles, and sprite sheets that games, collecting, and nurturing products need, see "Asset sets" below.

## Let the image carry meaning first

Before generating, write one sentence: what should this image make someone understand at a glance? If you cannot answer, do not generate yet. "A nice-looking usage scene" is not an answer. "The product turned a pile of chaos into these few clear results" is.

Encode the information through contrast. Unify the whole image in one quiet material or color, such as a white model, monochrome, defocus, or silhouette, and let only the few places that carry information have color, light, or detail. For example, in a white warehouse model only the two shelf rows with anomalies glow orange. On a grayscale map only the route being delivered right now is in color. When everything is equally detailed, nothing is a focal point. The first version usually fails exactly this way.

Choose a subject that can "connect" to the page:

- A single object that can cross the boundary between two color fields.
- A line that can extend out of the frame: cables, rails, rivers, film, paper tape.
- A space you can annotate: a model, a map, a section, a floor plan.

Such a subject can later join the page's lines, annotations, and sections into one piece. A self-contained landscape photo cannot.

## Writing the prompt

Write in a fixed order, one or two sentences per item:

1. **Subject and form**: what the thing is and in what genre it appears (photo, illustration, model, or diagram). Derive the genre from the page's direction.
2. **Composition and white space**: where the subject sits in the frame and how much it occupies, and which area stays empty for text. For example, "place the subject on the right at x=60–90%, keep the left 50% completely clean for typography." The empty area must have no highlights, reflections, or busy texture, so the text stays clear and readable.
3. **Safe distance**: the subject, its plinth, and its shadow must not touch the text edge. Leave a gap of about 10%, so text does not land on the object when the screen narrows.
4. **Background**: write the exact hex value the page uses (such as `#080D18` or `#F9F8F5`), or ask for a fully transparent background. When the values match, the edges blend into the page naturally, with no extra CSS mask to patch them.
5. **Material and light**: key light direction, fill light, and surface quality. Use the same light direction for every image on one page. Floor reflections fade naturally toward the empty side and do not sweep across the text area.
6. **Exclusions**: no text, logos, pseudo-code, interface screenshots, or stray floating objects. For small icons or transparent images, state "no ground shadow". Leave the outer shadow to the front end with CSS `filter: drop-shadow(...)`.

Text, interfaces, and buttons are always set in real HTML/CSS, never drawn by the image model. Image models get text wrong, it cannot be edited, and it cannot be selected or read by a screen reader. Images are responsible only for objects, materials, and light.

## Judge it inside the page after generating

Look at it in the real page at real size, not in an image viewer. An image that looks great alone often turns out too full, facing the wrong way, or with the empty space in the wrong place once it is in the layout.

If it is wrong, change the prompt and regenerate, and write down exactly what to change, such as "move the subject right and leave half the space on the left" or "remove the floor reflection and change the background to #080D18". Do not rework the layout around an unsuitable image. From one batch, pick the image that lays out best, not the one with the most detail.

## Make the image and the page one piece

**Background blending.** For an opaque image, sample the actual color from its four corners and use the same value for the page background. Fade all four edges into that color. No frame, and no rounded card. The fade can be a CSS mask, or you can fade the edges directly into the page color on export. When the background is a solid color and the prompt's background color matches the page exactly, the edges blend seamlessly on their own.

**Transparent images.** Place them on the final background first and check the edges, white fringes, and leftover checkerboard. Check the alpha channel by looking at pixels, not at the file extension. Do not bake the shadow into the image. Let the page add the drop shadow against the actual background, so it stays correct when the background changes.

**Crossing structure.** Place a transparent object on the boundary between two color blocks or two sections, so it belongs to both sides at once.

**Image and code hand off.** The generated image handles the materials and light that code cannot produce, such as metal, glass, models, and lighting. Code handles the parts that need to be precise, editable, and continuous, such as the lines, paths, and annotations that extend out of the image. If part of the image should continue into the page, crop it out and continue it as vectors. That way it can cross the layout precisely, carry real text, and reroute at different widths.

**Annotations.** Annotate on the image with thin leader lines and text, not with speech-bubble cards that have fills and shadows. Leader endpoints must land on real positions in the image: give the image a fixed size and position in the layout and convert coordinates from image pixels. On narrow screens, hide the annotations or turn them into a list below the image. Do not let them drift to the wrong positions.

**Narrow-screen cropping.** Do not shrink a whole large scene proportionally until it is illegible. Crop the focal area out of the original and save a separate image for narrow screens, or use object positioning to aim at the focal point. Both the desktop crop and the phone crop must keep the few places that carry information.

**Use one image several times.** The closing section or another section can use a close-up of a detail from the same image. That is more consistent than generating another image whose light and style do not match.

## Let one painting be the stage

Another use is the exact opposite: the image carries no information and only gives mood, the interface stays restrained in black and white, and one painting with visible brushwork is the page's only source of color, such as an oil painting, gouache, watercolor, or a print.

- **The painting is the stage, and the interface performs on it.** Place a simplified version of the real interface on top of the painting, with the painting showing around the edges. When scrolling, the painting stays fixed and only the interface content in front changes, which connects to "scroll narrative".
- **Crop boldly.** Keep only one corner or one detail of the painting, close to abstract, so it does not compete with the interface. The subject need not relate to the product literally, but the temperament must match: fast, quiet, warm, or relaxed.
- **Loose and tight set each other off.** The looser the painting, the more precise and clean the interface must be. Together, each makes the other look better.
- **Use it sparingly.** One painting runs through the whole page, or appears in only two or three places, such as the top of the pricing card and the footer. Do not give every section its own painting. Keep one medium and one brushwork across the page.
- **Demonstrate with a simplified real interface.** Blur the secondary content or replace it with a skeleton, and make only the one point you are explaining clear. Draw numeric comparisons directly with interface elements, such as two progress bars of different lengths, instead of making a separate chart.

## Unifying mixed assets in monochrome

When you bring in historical paintings, sculpture portraits, or outside photography, color bitmaps easily clash with the interface's theme colors. A unified monochrome treatment pulls assets from different sources into the current direction:

- **Monochrome mapping**: convert the asset to high-contrast black and white, then map the darks and lights to the page's primary color and paper color (for example pure blue and bone white), so the foreign image reads like print hatching or screen printing.
- **Halftone and dither**: apply halftone dots or faint digital scan lines to realistic photos. This dissolves the photographic realism and makes them read more like technical diagrams or engineering charts, so they sit more naturally with typography and the grid. Dither is more than a style. It naturally removes the banding common in smooth dark gradients, and high-frequency dot patterns compress extremely well as WebP, so a few dozen KB can carry a large, sharp image.
- **Classical objects as the visual focus**: products without a physical form, such as low-level algorithms, AI models, or protocols, can borrow physical objects such as sculptures or architectural fragments as the visual focus, then unify the texture with halftone or faint scan lines, so classical weight and modern technology create tension.

## Deriving a key visual for abstract technology

When there is no product screenshot to show, do not fall back to the generic glowing colored orb or the big gradient. Derive the key visual from a concrete object or craft form instead. It is distinctive and it protects the clarity of the typography:

- **Etching line art and topology markings (infrastructure, compilers, databases)**: fine hatching in the manner of engineering manuscripts, combined with coordinate crosshairs and topological connections. A natural fit for monospace type and pure code interfaces.
- **Print registration and paper craft (tools, communities, media)**: registration marks, micro-serrated torn edges, paper creases, or coarse halftone. They carry the feel of printed matter and suit a light paper background.
- **A real plinth (SaaS, modern tools, lifestyle)**: place the core object on rough limestone, frosted acrylic, or a raw wood tray under controlled natural light, with the subject to one side, leaving a large clean background for text.
- **Industrial macro and mechanical perspective (hardware, chips, manufacturing)**: cool-lit perspective views of mechanical structures or micro wafer components, with internal circuitry faintly visible, conveying precision and certainty.

What these approaches share: large areas of controlled tone keep the typography from clashing with color, and the wireframes and scales inside the image can be continued by real SVG/CSS.

## Asset sets: characters, props, and sprite sheets

Games, collecting, and nurturing products do not need one image. They need a whole set of assets that will be placed, flipped, and compared again and again.

- **Write the style guide first.** One sentence each for drawing style, viewpoint, light direction, material, proportions, and palette. Every prompt in the batch follows it.
- **Distinguish a series by silhouette.** Keep proportions and light direction constant, and tell individuals apart by silhouette features such as ears, props, and accessories, not just color. They must still be distinguishable at a glance when shrunk to actual display size.
- **Derive multiple states from one image.** Growth stages, front and back, before and after the shell opens, and different actions are edited as variants from the first image as the reference, so they stay the same character. Align the contact point of every state to the same baseline.
- **Cut transparent sprite sheets by silhouette.** Leave transparent gaps between cells and cut along the actual silhouette, not into equal cells, otherwise you cut off the treetop or drag in fragments from the neighboring cell. Check alpha pixels, not the preview's background color, then look at the edges on the final background.
- **Anything attached to an object must work from both sides.** Assets that flip, fall, or turn sideways need both a front and a back, with edges closed along the silhouette. Leave the lighting to the scene. Do not bake shadows into the image that point against the scene's light.

## Files and notes

- Export at 2× the display size. Do not inline the original large image directly. Use JPEG or WebP for opaque images, and WebP or PNG for transparent ones. Keep each image within a few hundred KB. Inlining as a data URL grows the size by roughly another third.
- Keep the prompt, the original, and the processed version, and write down the purpose and the processing of each image.
- Generated images do not impersonate real products, real places, or real people. Write "the images are AI-generated" in the delivery notes, not in the interface.
