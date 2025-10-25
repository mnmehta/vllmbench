#!/bin/bash
# Hardcode this for now since install_llmd.py hardcodes it in the name=infra-... label
export MLFLOW_TRACKING_URI=http://169.63.180.173:5000
export RELEASE_NAME_POSTFIX=inference-scheduling 
turns=10
run_name="multiturn_run_chatendpoint"
seed=999999

declare -a install_opts=(
  "--config-name default install.well_lit_path=guides/inference-scheduling"
)

# Labels aligned by index with install_opts
declare -a install_labels=(
  "qwen-approx"
)

# Run the suite at replicas 2, 4, and 8, sweeping active conversations {1..512} (powers of 2)
for replicas in 8; do
  for idx in "${!install_opts[@]}"; do
    install_options="${install_opts[$idx]}"
    label="${install_labels[$idx]}"
    # Install once per config/replica count
    python -u install_llmd.py $install_options install.decode_replicas=$replicas install.gaie_helmfile_overrides='["gaie_image_override.yaml"]'
    # Then sweep run-only options
    for mac in 32; do
      run_options="multiturn.experiment_name=multiturn_sweep_test"\
" multiturn.input.prompt_input.num_turns.min=$turns"\
" multiturn.input.prompt_input.num_turns.max=$turns"\
" multiturn.run_name=${run_name}_${label}_replicas${replicas}_mac${mac}"\
" multiturn.max_active_conversations=$mac"\
" multiturn.input.num_conversations=$mac"
      python -u bench_multiturn.py $install_options $run_options multiturn.seed=$seed install.decode_replicas=$replicas
      ((seed++))
    done
  done
done
