#!/bin/bash
# Hardcode this for now since install_llmd.py hardcodes it in the name=infra-... label
export MLFLOW_TRACKING_URI=http://169.63.180.173:5000
export RELEASE_NAME_POSTFIX=inference-scheduling 
turns=10
run_name="multiturn_run2"
run_options="multiturn.experiment_name=multiturn_sweep multiturn.input.prompt_input.num_turns.min=$turns multiturn.input.prompt_input.num_turns.max=$turns multiturn.run_name=$run_name"

declare -a install_opts=(
  "--config-name llama70b install.gaie_helmfile_overrides='[\"gaie_plugins.yaml\"]'"
  "--config-name llama70b_precise"
  "--config-name llama70b"
  "--config-name default install.well_lit_path=guides/inference-scheduling install.gaie_helmfile_overrides='[\"gaie_plugins.yaml\"]'"
  "--config-name default install.well_lit_path=guides/precise-prefix-cache-aware"
  "--config-name default install.well_lit_path=guides/inference-scheduling"
)

for install_options in "${install_opts[@]}"; do
  python -u install_llmd.py $install_options
  python -u bench_multiturn.py $install_options $run_options
done