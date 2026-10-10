# Oil UI, English edition

This directory is a complete English translation of the [oil-oil/oil-ui](https://github.com/oil-oil/oil-ui) skill. It is self-contained: `SKILL.md`, the reference documents, the scripts, the assets, and the tests all live here, so the directory can be installed as a skill on its own. The upstream Chinese files at the repository root are untouched, which keeps `git merge upstream/main` conflict-free.

The pinned upstream commit and version are in `translation/UPSTREAM`. The frontmatter `version` in `SKILL.md` repeats that upstream version so the update checker can compare against upstream releases.

## Install

The skill is named `oil-ui-en`. Pick one route.

With the skills CLI. The repository root has its own `SKILL.md`, so discovery needs `--full-depth` to reach this directory:

```bash
npx skills add shubhamd/oil-ui-english --full-depth --skill oil-ui-en
```

By hand, for Claude Code. Clone the repository and link this directory into the skills folder:

```bash
git clone https://github.com/shubhamd/oil-ui-english.git
ln -s "$PWD/oil-ui-english/en" ~/.claude/skills/oil-ui-en
```

Do not install the Chinese `oil-ui` and this edition side by side. They answer the same requests and will compete.

## What differs from upstream

Everything that carries language is translated: the skill text, the thirteen reference documents, script messages and help output, lint labels, code comments, the style-card example config, and the tests. Four deliberate adaptations go beyond translation:

- The skill is named `oil-ui-en` so it can be installed next to the root skill without a name clash.
- `scripts/check_update.py` only notifies. Upstream's updater would replace this directory with the Chinese skill, so the English checker reports a newer upstream version and points here instead of running the updater.
- `scripts/build_style_cards.py` defaults `lang` to `en`. The explorer and the style cards keep their Chinese locale strings, so a Chinese conversation still gets a Chinese comparison page when the manifest says `"lang": "zh"`.
- Rules that are specific to Chinese typography (body size, heading line height, line breaking) stay explicitly about Chinese text, because the product being designed may be Chinese. Rules that meant "the product's language" say that.

## Keep it in sync with upstream

In Claude Code, the project skill `/translate-upstream` (`.claude/skills/translate-upstream/SKILL.md`) runs the whole procedure below, and a SessionStart hook in `.claude/settings.json` prints a reminder whenever `upstream/main` is ahead of the pinned commit. By hand:

```bash
git remote add upstream https://github.com/oil-oil/oil-ui.git   # once
git fetch upstream
git merge upstream/main                      # never conflicts: nothing under en/ exists upstream
python3 en/translation/sync_upstream.py      # lists what changed since the pinned commit
python3 en/translation/sync_upstream.py --diff    # prints the upstream patch for each file to re-translate
python3 en/translation/sync_upstream.py --apply   # copies language-free files (fonts, vendor) into en/
```

Translate the listed files with `translation/GLOSSARY.md` as the term list, bump `version` in `en/SKILL.md`, then:

```bash
python3 en/translation/sync_upstream.py --pin
python3 -m unittest discover -s en/tests
```

`en/tests/test_translation.py` fails when any prose still contains Chinese, when a reference document is missing or extra, when heading or table-row counts drift from upstream, when a relative link or anchor is broken, or when the pinned version falls behind the upstream `SKILL.md`. The sync script exits 1 while translatable changes remain, so an agent can loop on it.

## Layout

| Path | What it is |
| --- | --- |
| `SKILL.md`, `references/` | The translated skill and its reference documents |
| `scripts/`, `assets/` | Translated copies of the tools and the files they need |
| `tests/` | Upstream's tests adapted to the English strings, plus `test_translation.py` and `test_sync_upstream.py` |
| `translation/GLOSSARY.md` | Fixed English renderings for recurring terms |
| `translation/UPSTREAM` | The upstream commit and version this translation was made from |
| `translation/sync_upstream.py` | Reports and applies upstream changes since the pin |
