#! /bin/bash
pod=llmdbench-inference-perf-launcher
oc cp . ${pod}:vllmbench
oc rsh $pod bash -c "TARGET_TYPE=gateway MLFLOW_TRACKING_URI=http://169.63.180.173:5000 python vllmbench/bench.py $*"
#oc rsh $pod bash -c "TARGET_TYPE=gateway MLFLOW_TRACKING_URI=http://169.63.180.173:5000 python vllmbench/bench.py --config-name llama70b"
#oc rsh $pod bash -c "TARGET=http://10.130.0.166:8000 TARGET_TYPE=direct MLFLOW_TRACKING_URI=http://169.63.180.173:5000 python vllmbench/bench.py --config-name llama70b"
