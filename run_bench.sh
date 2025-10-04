#! /bin/bash
for config in default llama70b
do
  python install_llmd.py --config-name $config
  MLFLOW_TRACKING_URI=http://169.63.180.173:5000 python bench.py --config-name $config run.concurrencies='[3,4]' run.queries_per_user=1 run.experiment_name=test2
done
