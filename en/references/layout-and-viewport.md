# Layout and viewport

## Exact recreation

First record the reference image's logical viewport or known pixel size, its full extent, and any fixed regions. Image pixels are not the logical viewport. When you cannot determine it, state your assumption.

Measure the proportions of the main regions, the shared alignment lines, the text scale, the image crops, and the spacing relationships. Align the overall geometry and the typefaces first, then handle borders, shadows, and details. Do not re-explore the style because the task is a recreation.

Check differences with a viewport and content comparable to the reference. Fill in narrow screens and states the reference does not show according to the content constraints, and distinguish "recreated from the reference" from "reasonable extension".

Judging the likeness yourself usually comes out optimistic. A single full-page thumbnail also cannot show how far font size, spacing, and alignment are off. After each round of changes, run the screenshot tool's `--compare` to produce a comparison image (see [Tools](tools.md)). Fix the cells with the largest differences first, then check alignment lines, font sizes, and image crops in the overlay. Do not declare "recreated" from impression.

## What to verify

Actually check long content, empty content, and the states related to the current change. On mobile, watch for viewport changes, the input panel, and safe-area insets. The primary action must not be covered by the keyboard or a fixed region.

Check whether the page overflows horizontally by accident, whether scrolling happens in the expected region, whether focus and menus are visible, and whether the reading and operating order stays clear after zooming or reflow.
