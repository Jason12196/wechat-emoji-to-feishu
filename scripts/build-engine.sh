#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
"${PYTHON:-python3}" - "$project_dir" <<'PY'
import os
import shlex
import subprocess
import sys
from pathlib import Path

project = Path(sys.argv[1]).resolve()
environment = os.environ.copy()
encoded = environment.get("CARGO_ENCODED_RUSTFLAGS")
flags = (encoded.split("\x1f") if encoded else []) if encoded is not None else shlex.split(
    environment.get("RUSTFLAGS", "")
)
# Cargo's encoded separator keeps paths containing spaces as a single argument.
# The more specific project mapping follows the home mapping.
flags.extend([
    f"--remap-path-prefix={Path.home()}=/build/home",
    f"--remap-path-prefix={project}=/build/wechat-emoji-to-feishu",
])
environment["CARGO_ENCODED_RUSTFLAGS"] = "\x1f".join(flags)
subprocess.run([
    "cargo", "build", "--locked", "--release", "--manifest-path",
    str(project / "vendor/wxemoticon/cli/Cargo.toml"),
], env=environment, check=True)
PY
mkdir -p "$project_dir/runtime/bin"
cp "$project_dir/vendor/wxemoticon/cli/target/release/wxemoticon" "$project_dir/runtime/bin/wxemoticon"
printf '%s\n' "Built $project_dir/runtime/bin/wxemoticon"
