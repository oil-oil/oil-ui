#!/bin/sh
# Find a usable Python 3 at load time; when none exists, remind once and let the task continue.
script_dir=${0%/*}
if [ -n "$OIL_NO_UPDATE_CHECK" ] || [ -e "$script_dir/../.git" ] || [ -e "$script_dir/../../.git" ]; then
    exit 0
fi
state_base=${XDG_STATE_HOME:-${LOCALAPPDATA:-$HOME/.local/state}}
marker="$state_base/oil/update-python-missing"
for interpreter in python3 python; do
    if command -v "$interpreter" >/dev/null 2>&1 && "$interpreter" -c 'import sys; sys.exit(0 if sys.version_info[0] == 3 else 1)' >/dev/null 2>&1; then
        rmdir "$marker" 2>/dev/null
        exec "$interpreter" "$script_dir/check_update.py" "$@"
    fi
done
# mkdir's exclusive create keeps back-to-back and concurrent loads from reminding twice.
missing_python_notice() {
    printf '%s\n' 'Version checks need Python 3. This update check did not run.'
}
mkdir -p "$state_base/oil" 2>/dev/null
if mkdir "$marker" 2>/dev/null; then
    missing_python_notice
elif [ -d "$marker" ]; then
    printf '%s\n' 'OIL_UPDATE_CHECK_SKIPPED: missing_python'
else
    # When the state directory is not writable, the host remembers this reminder.
    missing_python_notice
fi
exit 0
