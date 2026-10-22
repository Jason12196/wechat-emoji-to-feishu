#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cargo build --locked --release --manifest-path "$project_dir/vendor/wxemoticon/cli/Cargo.toml"
mkdir -p "$project_dir/runtime/bin"
cp "$project_dir/vendor/wxemoticon/cli/target/release/wxemoticon" "$project_dir/runtime/bin/wxemoticon"
printf '%s\n' "Built $project_dir/runtime/bin/wxemoticon"
