# Assets

## Treat assets as the starting point of the design

A good asset can carry the whole page's mood, object recognition, or center of information. First ask "if only one image, one heading, and one action remained, which image deserves this spot", then decide whether more modules are needed. Do not treat assets as decoration filled in after the layout is done.

Follow the design north star to decide the image's subject, viewpoint, scale, light, color, material, and white space. The page's typography, background, edge treatment, and motion build their echoes from this image. A single controlled contrast can also set off the primary action. Unity means a shared visual logic, not the same filter applied to every image.

Dashboards and tools need asset judgment too: object thumbnails help recognition, content covers support browsing, maps or spatial diagrams help orientation, and necessary diagrams explain relationships. They can become the most valuable part of the interface. Do not default to tables and cards only because "this is a dashboard". When a pure data task truly does not benefit, keep the clear data presentation and do not force in mood imagery.

Assets must become structure, not illustrations in a box: let them cross the layout's boundaries, fill the first screen, or overlap with text. A page can be a complete world rather than "one page with one image".

Put the key asset into the real page and look at it once before extending to other areas. While assets are not in place, do not treat an aesthetic review of the placeholder version as a final pass.

When no suitable asset exists and the host already has image generation available, make the key asset yourself and give it a clear visual job. Do not skip this step because you are writing front-end code. When excellent assets already exist, design around them, and do not regenerate just to prove a tool was used. Without such capability, keep a clear asset brief and a list of what remains to be done.

## Decide the expressive job first

Judge whether the current gap comes from information and composition, or from the lack of an asset that can express the product and the brand. Do not use more images, glow, and animation to cover up hierarchy problems, and do not replace a necessary image with generic gradients and geometric shapes only because the code is easy to write.

Assets can show an object, explain a relationship, or build brand or mood. Decide the content, position, size ratio, cropping, background, and contrast with text first, then choose between existing resources, photography, illustration, or generated assets.

Keep the asset brief executable: what to express, what the subject is, where it goes, how it crops on wide and narrow screens, where it carries text, and which details must not be lost. If the image already expresses the theme, cut repeated explanation. Areas with text on top need stable light and dark values and enough room.

## Images and editable interfaces

Look at the input images before citing their features. Reuse resources of suitable quality with a reason for use. Generate or redraw only when they fall short. Keep the original files and their source, and distinguish reuse, cropping, generation, and post-processing.

Interface text, buttons, forms, data labels, and regular layout are expressed with editable elements. Photography, illustration, and special visuals go in clear containers. Do not use a full screenshot as an interactive deliverable.

Hand asset needs to the generation tools available in the host and follow the tool's own input and editing rules. For how to make a generated image carry meaning, how to write the prompt, and how to make the image and the page one piece, see [Imagery](imagery.md).

When an image is missing, reserve a suitable container and state the gap. Do not install tools automatically, switch to paid services, or ask the user to paste keys into the conversation. Substitute assets must not impersonate real product screenshots.

Keep one subject scale, viewpoint, light, and edge quality across a set of assets, so you do not end up with several images that each look good and have nothing to do with each other. Generated assets do not impersonate real scenes or product evidence. The final delivery keeps the source and purpose of each asset, the web page sizes files for the actual display size, and important subjects must hold up in both the desktop and the phone crop.

## Real-time 3D

Use real-time 3D in three situations: an object the user wants to rotate and inspect, physics such as stacking, collision, pushing, and swinging, and materials that change with the viewing angle, such as glass, metal, and clear plastic. When one generated image can express it, or when it is only there to look premium, do not use it.

- Use a mature engine such as three.js, and add a rigid-body library only when physics is needed. Generated images serve as textures, sprites, or environment light sources. Code is responsible for space, movement, and forces.
- Accept by looking at the picture, not by whether a library was used: a still frame shows volume and perspective, objects have contact shadows, and materials stay distinguishable with the glow turned off. In a screen recording, movement is continuous and force carries into the object being pushed.
- For a new preview, download the library into `vendor/` in the task directory with its license, and do not reference a CDN. In an existing project, bring it in the way the project already manages dependencies. Pages and textures loaded as modules must be opened through a local server. When the page must open by double-click, bundle it as one plain script, with textures inlined or in the same directory.
- Cap the device pixel ratio at 2. Stop rendering frames when the page is hidden or scrolled out of the viewport. When WebGL is unavailable, show a static image of the same scene. Under reduced motion, still compute the results as usual and only turn off camera shake and decorative performances.
- Confirm the canvas really painted content before taking screenshots, see [Tools](tools.md).

## Generated video as an optional path

When you need a loopable asset that can be layered, verify the seam between the end and the start, the subject's edges, and the background treatment first. A solid background plus keying is only one candidate technique. Transparent and reflective objects may lose edges or spill color, so check them on the final page background.

When you need continuous narrative, use the last frame of the previous segment to lead into the first frame of the next, or plan consistent keyframes. When playback is controlled by scroll or gestures, check seeking, reverse playback, loading, and memory use. Do not decode the whole video into a full set of large images by default.

For objects that need refraction or translucency, such as glass and crystal, generate the picture on the final page's background color first, so the refraction and shadows are baked into the asset, then remove the background with a video keying model. Generating directly on a green screen and keying afterwards leaves green in the refraction. Pre-rendered refraction and lighting correspond only to the background they were generated against. Do not promise real-time physical effects that follow arbitrary page content.

Videos with a transparent background can straddle the boundary between two sections, like images. See "Crossing structure" in [Imagery](imagery.md).
