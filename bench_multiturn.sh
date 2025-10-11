#!/bin/bash
# Hardcode this for now since install_llmd.py hardcodes it in the name=infra-... label
export MLFLOW_TRACKING_URI=http://169.63.180.173:5000
export RELEASE_NAME_POSTFIX=inference-scheduling 

python -u  install_llmd.py --config-name llama70b_precise
for turns in 10 ; do
  python -u  bench_multiturn.py --config-name llama70b_precise multiturn.experiment_name=multiturn_sweep multiturn.input.prompt_input.num_turns.min=$turns multiturn.input.prompt_input.num_turns.max=$turns
done
python -u  install_llmd.py --config-name llama70b
for turns in 10 ; do
  python -u  bench_multiturn.py --config-name llama70b multiturn.experiment_name=multiturn_sweep multiturn.input.prompt_input.num_turns.min=$turns multiturn.input.prompt_input.num_turns.max=$turns
done

python -u  install_llmd.py --config-name default install.well_lit_path=guides/precise-prefix-cache-aware
for turns in 10 ; do
  python -u  bench_multiturn.py --config-name default install.well_lit_path=guides/precise-prefix-cache-aware multiturn.experiment_name=multiturn_sweep multiturn.input.prompt_input.num_turns.min=$turns multiturn.input.prompt_input.num_turns.max=$turns
done
python -u  install_llmd.py --config-name default install.well_lit_path=guides/inference-scheduling
for turns in 10 ; do
  python -u  bench_multiturn.py --config-name default install.well_lit_path=guides/inference-scheduling multiturn.experiment_name=multiturn_sweep multiturn.input.prompt_input.num_turns.min=$turns multiturn.input.prompt_input.num_turns.max=$turns
done