#! /bin/bash
# Hardcode this for now since install_llmd.py hardcodes it in the name=infra-... label
export RELEASE_NAME_POSTFIX=inference-scheduling 
python install_llmd.py --config-name llama70b_precise
python bench.py --config-name llama70b_precise run.experiment_name=approximate_vs_precise
python install_llmd.py --config-name llama70b
python bench.py --config-name llama70b run.experiment_name=approximate_vs_precise

python install_llmd.py --config-name default install.well_lit_path=guides/precise-prefix-cache-aware
python bench.py --config-name default install.well_lit_path=guides/precise-prefix-cache-aware run.experiment_name=approximate_vs_precise
python install_llmd.py --config-name default install.well_lit_path=guides/inference-scheduling
python bench.py --config-name default install.well_lit_path=guides/inference-scheduling run.experiment_name=approximate_vs_precise
exit
for wlp in precise-prefix-cache-aware inference-scheduling; do
  for config in default llama70b; do
    python install_llmd.py --config-name $config install.well_lit_path=guides/$wlp
    python bench.py --config-name $config run.experiment_name=approximate_vs_precise
  done
done
