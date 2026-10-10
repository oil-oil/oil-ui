#!/bin/sh
# SessionStart hook: speak only when upstream has moved past the pinned translation commit.
root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
pin=$(sed -n 's/^commit //p' "$root/en/translation/UPSTREAM" 2>/dev/null)
[ -n "$pin" ] || exit 0
git -C "$root" remote get-url upstream >/dev/null 2>&1 || exit 0
git -C "$root" fetch upstream --quiet 2>/dev/null
head=$(git -C "$root" rev-parse upstream/main 2>/dev/null) || exit 0
[ "$head" = "$pin" ] && exit 0
count=$(git -C "$root" rev-list --count "$pin..$head" 2>/dev/null || echo "some")
printf 'Reminder: upstream oil-ui has %s new commit(s) since the English edition was last translated (pinned %.7s, upstream/main now %.7s). Tell the user and ask whether to run /translate-upstream now. If they say yes, run that skill.\n' "$count" "$pin" "$head"
exit 0
