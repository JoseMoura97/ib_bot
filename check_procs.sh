#!/bin/bash
for f in /proc/[0-9]*/cmdline; do
    pid=$(echo "$f" | cut -d/ -f3)
    cmd=$(cat "$f" 2>/dev/null | tr '\0' ' ')
    if echo "$cmd" | grep -qi python; then
        echo "PID=$pid: $cmd"
    fi
done
echo "---"
echo "QUIVER_API_KEY set: $(test -n \"$QUIVER_API_KEY\" && echo yes || echo no)"
echo "Cache dir:"
ls -la /app/.cache/ 2>/dev/null | head -10
