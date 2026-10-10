---
name: translate-upstream
description: Use when upstream oil-oil/oil-ui has new commits and the English edition in en/ must catch up, when the session-start reminder says upstream moved past the pinned commit, or when the user asks to sync, update, or re-translate the English skill.
---

# Translate upstream changes

The repository root is the Chinese upstream skill, never edited here. `en/` is the English edition, pinned to one upstream commit in `en/translation/UPSTREAM`. This skill carries the pin forward: merge upstream, translate only what changed, re-pin, prove it with the tests.

## Steps

1. **Merge upstream.** `git fetch upstream && git merge upstream/main`. It cannot conflict, because nothing under `en/` exists upstream. Add the remote first if `git remote get-url upstream` fails: `https://github.com/oil-oil/oil-ui.git`.
2. **List the work.** `python3 en/translation/sync_upstream.py --diff`. Exit 0 means nothing to translate. Stop and say so. Otherwise it prints each changed file as `translate` or `passthrough`, followed by the upstream patch of every `translate` file.
3. **Copy passthrough files.** `python3 en/translation/sync_upstream.py --apply` copies fonts, vendor scripts, and the logo into `en/`.
4. **Translate the deltas.** For each `translate` file, apply the upstream patch to its `en/` counterpart. Translate the changed hunks, keep untouched text as it is. A new upstream file gets a full translation. A deleted upstream file is deleted under `en/`. With more than three files, fan out with one fork agent per file group and hand each the rules below.
5. **Bump and pin.** Set `version` in `en/SKILL.md` to the upstream `SKILL.md` version, then `python3 en/translation/sync_upstream.py --pin`.
6. **Prove it.** `python3 -m unittest discover -s en/tests`. `test_translation.py` fails on leftover Chinese, missing or extra documents, heading or table-row drift, broken links or anchors, and a stale pin. Two explorer tests (`test_rendered_interfaces_do_not_mix_languages`) time out on machines where headless Chrome's debugging pipe never answers, upstream included. Report them as environmental only if they also fail on the untouched root suite.
7. **Report.** List the files translated, the judgment calls, and the test counts. Do not commit unless asked.

## Translation rules

- Read `en/translation/GLOSSARY.md` first and use its renderings. One word for one concept across all files.
- Every sentence of the source appears with the same meaning, bluntness, numbers, flags, paths, code spans, tables, lists, headings, and link targets. Nothing summarized, softened, or added.
- Imperative second person. Short sentences. No em dashes, no semicolons, no "not just X but Y".
- In-page anchors are the GitHub slug of the English heading. Quoted section names in prose must match the real English heading in the target file. Check with the quoted-phrase sweep in `test_translation.py` and by grep.
- Zero CJK in `en/SKILL.md` and `en/references/`. In code, CJK stays only in runtime locale data (the explorer's `zh` I18N block, the `zh` label tables, `MESSAGES["zh"]`), the CJK-detection regexes, and test fixtures that exercise the Chinese-interface rules.
- Rules specific to Chinese typography stay about Chinese text. Rules that mean "the product's language" say that.

## Deliberate differences to preserve

These are not translation drift. Keep them when porting upstream changes:

| File | Difference |
| --- | --- |
| `en/SKILL.md` | `name: oil-ui-en`. English-only description. "This skill is written in English" sentence. Pro link defaults to `/en/pro/`. |
| `en/scripts/check_update.py` | Notify-only. Looks up upstream `oil-ui` on the version API, never runs oil-cli. Port logic changes, never the updater. |
| `en/scripts/check_update.sh` | English-only notice, also skips when `../../.git` exists. |
| `en/scripts/build_style_cards.py` | `lang` defaults to `"en"`. |
| `en/assets/style-cards/example.json` | English pottery-studio sample with Latin fonts. |
| `en/README.md`, `en/translation/` | Exist only here. |
