# Play and tactile controls

Mini-games, lotteries, gacha, timed nurturing, and tactile controls such as knobs, levers, and joysticks: here the process itself is the product. Users come to watch the reels slow down, the coin get pushed over the edge, the plush toy almost slip. For these interfaces read this file first. The other rules still apply as usual.

## The process is the game

- The performance may run longer than an ordinary interface switch. Three reels stopping one after another over about 2 seconds, for example, is not cut short by "past 500ms people wait".
- Once a fee is charged or a result is out, save it first: a refresh loses nothing, nothing is charged twice, a reward settles exactly once. When to save is decided by the gameplay.
- State clearly which operations are locked during the performance. Repeated taps must not charge again.
- Gestures on knobs and levers follow the finger from the point of press. A gesture counts only after passing the trigger point. Releasing before that charges nothing.
- Under reduced motion, the gameplay still computes its result as usual. Only the picture is placed directly. The gameplay itself must not be stopped.
- Judge feel from a screen recording: is the deceleration continuous, is there a stutter at the stop, where does the payout fly from and to. Three frames can only show states.

## Assets and rendering

- Characters, collectibles, props, symbols, and material textures are the protagonists of these interfaces. Make them with image generation by default, and list the assets before starting. Hand-written SVG and CSS draw only interface icons and simple shapes. Use them for characters and props and the result lands at icon-pack quality. How to produce a set is in "Asset sets" in [Imagery](imagery.md). When the host cannot generate images, hand over an asset brief per [Assets](media.md). Do not pass off hand-drawn shapes as finished work.
- When the fun comes from space and physics, render the scene with real-time 3D, for example stacking, collisions, pushing, swinging, or transparent and metallic materials. Generated images serve as textures and sprites. The approach is in "Real-time 3D" in [Assets](media.md). Natural change such as trees growing or weather is usually better done with a set of generated images.
- Look again once the assets are in the scene: lighting matches the scene, there are contact shadows, and no paper edge shows from the side, the back, or when tumbling. An image having been generated does not mean it is believable once placed in the scene.
