#!/bin/bash

set -euo pipefail

HOWDONE="$(cd "$(dirname "$0")" && pwd)/howdone.py"
TMPBASE=$(mktemp -d)
trap 'rm -rf "$TMPBASE"' EXIT

PASS=0
FAIL=0

pass() { echo "PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $1 -- $2"; FAIL=$((FAIL+1)); }

assert_dir() {
    local dir="$1" label="$2"
    if [[ -d "$dir" ]]; then pass "$label"; else fail "$label" "directory not found: $dir"; fi
}

assert_file() {
    local file="$1" label="$2"
    if [[ -f "$file" ]]; then pass "$label"; else fail "$label" "file not found: $file"; fi
}

assert_contains() {
    local file="$1" pattern="$2" label="$3"
    if grep -q -e "$pattern" "$file" 2>/dev/null; then pass "$label"; else fail "$label" "pattern '$pattern' not in $file"; fi
}

assert_no_prefix_dir() {
    local parent="$1" prefix="$2" label="$3"
    local found
    found=$(find "$parent" -maxdepth 1 -name "${prefix}-*" -type d 2>/dev/null | head -1)
    if [[ -z "$found" ]]; then pass "$label"; else fail "$label" "unexpectedly found dir: $found"; fi
}

run_hd() { python3 "$HOWDONE" "$@"; }

# Minimal config used by many tests (no heavy side commands)
MINIMAL_COMMANDS='commands:
  side.txt: echo sideout'

#  Test 1: Auto-discover .howdone.yaml
T="$TMPBASE/t1"
mkdir "$T"
cat > "$T/.howdone.yaml" << EOF
prefix: autorun
output_file: output.txt
$MINIMAL_COMMANDS
EOF

(cd "$T" && run_hd "echo mainout") > /dev/null

OUTDIR=$(find "$T" -maxdepth 1 -name 'autorun-*' -type d 2>/dev/null | head -1)
assert_dir  "$OUTDIR"                      "t1: auto-discover .howdone.yaml — output dir created with prefix"
assert_file "$OUTDIR/meta.yaml"            "t1: meta.yaml written"
assert_file "$OUTDIR/output.txt"           "t1: main output file written"
assert_file "$OUTDIR/side.txt"             "t1: side-command file written"
assert_contains "$OUTDIR/output.txt" "mainout" "t1: main command output captured"

#  Test 2: Explicit config file via -c
T="$TMPBASE/t2"
mkdir "$T"
cat > "$T/my.yaml" << EOF
prefix: explicitrun
output_file: output.txt
$MINIMAL_COMMANDS
EOF

# Run from a directory that has no .howdone.yaml so we know -c is what works
(cd "$T" && run_hd -c "$T/my.yaml" "echo mainout") > /dev/null

OUTDIR=$(find "$T" -maxdepth 1 -name 'explicitrun-*' -type d 2>/dev/null | head -1)
assert_dir  "$OUTDIR"                      "t2: explicit -c config — output dir created"
assert_file "$OUTDIR/output.txt"           "t2: main output file written"
assert_file "$OUTDIR/side.txt"             "t2: side-command file written"
assert_contains "$OUTDIR/output.txt" "mainout" "t2: main command output captured"

#  Test 3: Output dir from prefix in config
T="$TMPBASE/t3"
mkdir "$T"
cat > "$T/.howdone.yaml" << EOF
prefix: cfgprefix
output_file: output.txt
commands: {}
EOF

(cd "$T" && run_hd "echo hi") > /dev/null

OUTDIR=$(find "$T" -maxdepth 1 -name 'cfgprefix-*' -type d 2>/dev/null | head -1)
assert_dir "$OUTDIR" "t3: prefix from config — dir named <config-prefix>-<timestamp>"

#  Test 4: Output dir from -p on the command line 
T="$TMPBASE/t4"
mkdir "$T"
cat > "$T/.howdone.yaml" << EOF
prefix: cfgprefix
output_file: output.txt
commands: {}
EOF

(cd "$T" && run_hd -p "cmdprefix" "echo hi") > /dev/null

OUTDIR=$(find "$T" -maxdepth 1 -name 'cmdprefix-*' -type d 2>/dev/null | head -1)
assert_dir "$OUTDIR" "t4: -p flag — dir named <cmd-prefix>-<timestamp>"
assert_no_prefix_dir "$T" "cfgprefix" "t4: config prefix not used when -p given"

#  Test 5: Output dir from -d on the command line 
T="$TMPBASE/t5"
mkdir "$T"
cat > "$T/.howdone.yaml" << EOF
prefix: someprefix
output_file: output.txt
commands: {}
EOF
EXACT="$T/my_exact_dir"

(cd "$T" && run_hd -d "$EXACT" "echo hi") > /dev/null

assert_dir  "$EXACT"              "t5: -d flag — exact directory created"
assert_file "$EXACT/output.txt"   "t5: output.txt in exact dir"
assert_file "$EXACT/meta.yaml"    "t5: meta.yaml in exact dir"

#  Test 6: output_dir.var passes env variable to main command
T="$TMPBASE/t6"
mkdir "$T"
cat > "$T/.howdone.yaml" << EOF
prefix: vartest
output_file: output.txt
output_dir:
  var: MY_OUTPUT_DIR
commands: {}
EOF

(cd "$T" && run_hd "printenv MY_OUTPUT_DIR") > /dev/null

OUTDIR=$(find "$T" -maxdepth 1 -name 'vartest-*' -type d 2>/dev/null | head -1)
assert_dir "$OUTDIR" "t6: output_dir.var — output dir created"
assert_contains "$OUTDIR/output.txt" "$OUTDIR" "t6: MY_OUTPUT_DIR env var received by main command"

#  Test 7: output_dir.var also passed to side commands
T="$TMPBASE/t7"
mkdir "$T"
cat > "$T/.howdone.yaml" << EOF
prefix: varside
output_file: output.txt
output_dir:
  var: MY_OUTPUT_DIR
commands:
  sideenv.txt: printenv MY_OUTPUT_DIR
EOF

(cd "$T" && run_hd "echo main") > /dev/null

OUTDIR=$(find "$T" -maxdepth 1 -name 'varside-*' -type d 2>/dev/null | head -1)
assert_contains "$OUTDIR/sideenv.txt" "$OUTDIR" "t7: MY_OUTPUT_DIR env var received by side command"

#  Test 8: output_dir.cd runs commands inside output dir
T="$TMPBASE/t8"
mkdir "$T"
cat > "$T/.howdone.yaml" << EOF
prefix: cdtest
output_file: output.txt
output_dir:
  cd: true
commands:
  workdir.txt: pwd
EOF

(cd "$T" && run_hd "echo main") > /dev/null

OUTDIR=$(find "$T" -maxdepth 1 -name 'cdtest-*' -type d 2>/dev/null | head -1)
assert_contains "$OUTDIR/workdir.txt" "$OUTDIR" "t8: output_dir.cd — side commands run in output dir"

#  Test 9: output_dir.arg appends output dir path as argument to main command
T="$TMPBASE/t9"
mkdir "$T"
cat > "$T/.howdone.yaml" << EOF
prefix: argtest
output_file: output.txt
output_dir:
  arg: "-o <OUTPUT_DIR>"
commands: {}
EOF

(cd "$T" && run_hd "echo") > /dev/null

OUTDIR=$(find "$T" -maxdepth 1 -name 'argtest-*' -type d 2>/dev/null | head -1)
assert_dir "$OUTDIR" "t9: output_dir.arg — output dir created"
assert_contains "$OUTDIR/output.txt" "-o $OUTDIR" "t9: output dir path appended as arg to main command"

#  Test 10: output_dir.arg appends output dir path as argument to main command as list
T="$TMPBASE/t10"
mkdir "$T"
cat > "$T/.howdone.yaml" << EOF
prefix: argtest
output_file: output.txt
output_dir:
  arg: ["-o", "<OUTPUT_DIR>"]
commands: {}
EOF

(cd "$T" && run_hd "echo") > /dev/null

OUTDIR=$(find "$T" -maxdepth 1 -name 'argtest-*' -type d 2>/dev/null | head -1)
assert_dir "$OUTDIR" "t10: output_dir.arg — output dir created"
assert_contains "$OUTDIR/output.txt" "-o $OUTDIR" "t10: output dir path appended as arg to main command as list"

#  Summary
echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
