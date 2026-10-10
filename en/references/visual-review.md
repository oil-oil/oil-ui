# Visual Review Dispatch Protocol (for the lead agent)

**System instruction**: this file is the dispatch manual the lead agent uses to call an independent subagent for quality control.
> ⚠️ **Warning**: you do **not** need to read the detailed scoring criteria and fault-finding rules. They are all in the [Reviewer Manual](reviewer-manual.md). To save your context and prevent memory mix-ups, just package the task and hand it to the subagent. Let it read that manual and report back to you.

## 1. When to dispatch, and which mode to trigger

When you have finished a key page, a design proposal, or a change, trigger the matching reviewer subagent by this list:

| What you changed | Prompt template for the subagent |
| --- | --- |
| Explored a new interface, or overturned the current state with a redesign (a reshape) | `Read references/reviewer-manual.md and, following the "Review of new interfaces and redesigns" standard, give this screenshot a merciless review with a score from 1 to 10.` |
| **Review of an existing interface**: tidying, upgrading, polishing, or extending an existing interface | `Read references/reviewer-manual.md and, following the "Polish review of an existing interface" standard, compare against the supplied current-state guidelines and point out deviations. No score.` |
| Small changes, a single spacing or color tweak | **No subagent needed.** The lead agent checks it in context. |

## 2. The handoff checklist the lead agent prepares before dispatch

When calling the host's isolated execution ability, you must supply the following:
- **Always**: screenshots or recordings of the current version (with the device viewport noted), the user's original task, the design boundaries and constraints. Hard constraints from the direction card that the reviewer needs to know, such as a brand requirement to show the wordmark on every screen, go in as one sentence in the constraints. Do not hand over the whole direction card.
- **If available**: the existing project's color guidelines and component constraints (mandatory for existing projects). When the project has `DESIGN.md` or a similar design document, hand the whole document to a polish review of an existing interface and treat it as the standard, while a new interface and redesign review only takes its brand assets and its "do not" items into the constraints.
- **The screenshot tool's default-pattern hints**: supply the hints from the `lint` field of `report.json` verbatim. For each item you decided to keep, attach one sentence of reasoning.
- **Never**: your source code, a defense of your thought process, or the old scores earlier subagents gave (scoring must be independent).

Screenshots must belong to the current version and be accessible to the reviewer. For long pages, provide both the full page and the necessary details. Detail shots cannot replace the overall composition.

**Motion evidence is mandatory for new interfaces and redesigns, not "if available":**
- For each of the three basic motions (primary-action feedback, one state change, first entrance), a 3–5 second recording or start, middle, and end frames, with the triggering action written down.
- For landing, brand, launch, and exhibition pages, also the evidence for scroll motion: a scroll recording or start, middle, and end frames for each scroll-driven narrative, with scroll positions written down, and recordings or three frames of the entrances of at least two different sections. See [Scroll narrative](scroll-narrative.md).
- The `report.json` of the screenshot tool contains the motion probe result. Hand it to the reviewer as well. When the probe reports "no animation detected", first check against [Tools](tools.md) whether it is a missed detection. If the motion really is missing, add it before sending for review.

When you cannot produce a piece of evidence, tell the reviewer truthfully which one is missing, and the review deducts for it as a defect. Without an isolated executor that can view images, the lead agent self-checks against the same manual and writes "not independently reviewed" on delivery. Without real screens, no visual score is given.

## 3. How the lead agent handles the subagent's feedback

After the subagent returns its report, you are the decision maker. Make changes by these principles:
- **The first item is "Redo"**: go back to the direction card and re-settle the skeleton or key visual of the named sections. Do not patch item by item.
- **Change in list order**: work the problem list from the highest impact down. Record the "Keep" line in the design notes and check against it while changing, so you do not sand it flat.
- **Items to follow without thinking**: the "useless copy that can be deleted outright" the subagent lists is **deleted by default** (unless that would create serious functional ambiguity).
- **Land it rationally**: map the subagent's high-level visual demands (such as "too crowded" or "unclear hierarchy") to your actual adjustments of CSS spacing, font sizes, and shadows. But when the subagent proposes changing a brand color or a large framework the user has locked, you may decline after writing a short reason.
- **Prevent endless loops**: when the two sides' aesthetic opinions reach a stalemate, flip back and forth, and bring no visible gain, keep the version you judge best and stop the loop.
