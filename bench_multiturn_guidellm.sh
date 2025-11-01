#!/bin/bash
# Co-authored by Cursor
# GuideLLM multi-turn sweep using bench_multiturn_guidellm.py

export RELEASE_NAME_POSTFIX=inference-scheduling 
experiment_name="guidellm_sweep"
run_name="guidellm_run4"

# Derive default turns from config (fallback to 5 if not found)
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
DEFAULT_YAML="$SCRIPT_DIR/conf/default.yaml"
turns_default=$(awk '/guidellm_multiturn:/ {f=1; next} f && /turns:/ {print $2; exit}' "$DEFAULT_YAML")
if [[ -z "$turns_default" ]]; then
  turns_default=5
fi

declare -a install_opts=(
  "--config-name llama70b install.gaie_helmfile_overrides='[\"gaie_plugins.yaml\"]'"
  "--config-name llama70b_precise"
  "--config-name llama70b"
  "--config-name default install.well_lit_path=guides/inference-scheduling install.gaie_helmfile_overrides='[\"gaie_plugins.yaml\"]'"
  "--config-name default install.well_lit_path=guides/precise-prefix-cache-aware"
  "--config-name default install.well_lit_path=guides/inference-scheduling"
)

# Labels aligned by index with install_opts
declare -a install_labels=(
  "70B-simple"
  "70B-precise"
  "70B-approx"
  "qwen-simple"
  "qwen-precise"
  "qwen-approx"
)

# Run the suite at replicas 2, 4, and 8
for replicas in 2 4 8; do
  for idx in "${!install_opts[@]}"; do
    install_options="${install_opts[$idx]}"
    label="${install_labels[$idx]}"
    # Install once per config/replica count
    python -u install_llmd.py $install_options install.decode_replicas=$replicas
    # Sweep request rates (duplicate first rate as warmup)
    for rate in 32 32 64 128 256 512; do
      # Compute dynamic params: prefix_count=2*rate, max_requests=2*rate*turns_default
      prefix_count=$((2 * rate))
      max_requests=$((2 * rate * turns_default))
      run_options="guidellm_multiturn.experiment_name=$experiment_name"\
" guidellm_multiturn.run_name=${run_name}_${label}_replicas${replicas}_rate${rate}"\
" guidellm_multiturn.rate=$rate"\
" guidellm_multiturn.data.prefix_count=$prefix_count"\
" guidellm_multiturn.max_requests=$max_requests"
      python -u bench_multiturn_guidellm.py $install_options $run_options install.decode_replicas=$replicas
    done
  done
done
