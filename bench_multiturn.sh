#!/bin/bash
# Hardcode this for now since install_llmd.py hardcodes it in the name=infra-... label
export MLFLOW_TRACKING_URI=http://169.63.180.173:5000
export RELEASE_NAME_POSTFIX=inference-scheduling 
turns=10
run_name="multiturn_run2"

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
  "70B-approx"
  "70B-precise"
  "70B-simple"
  "qwen-approx"
  "qwen-precise"
  "qwen-simple"
)

# Run the suite at replicas 2, 4, and 8, sweeping active conversations {1..512} (powers of 2)
for replicas in 2 4 8; do
  for idx in "${!install_opts[@]}"; do
    install_options="${install_opts[$idx]}"
    label="${install_labels[$idx]}"
    # Install once per config/replica count
    python -u install_llmd.py $install_options install.decode_replicas=$replicas
    # Then sweep run-only options
    for mac in 32 64 128 256 512; do
      run_options="multiturn.experiment_name=multiturn_sweep"\
" multiturn.input.prompt_input.num_turns.min=$turns"\
" multiturn.input.prompt_input.num_turns.max=$turns"\
" multiturn.run_name=${run_name}_${label}_replicas${replicas}_mac${mac}"\
" multiturn.max_active_conversations=$mac"\
" multiturn.input.num_conversations=$mac"
      python -u bench_multiturn.py $install_options $run_options install.decode_replicas=$replicas
    done
  done
done
