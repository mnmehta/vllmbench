#! /bin/bash
pod=llmdbench-inference-perf-launcher
oc cp bench.py ${pod}:bench.py
oc rsh $pod bash -c "TARGET_TYPE=gateway MLFLOW_TRACKING_URI=http://169.63.180.173:5000 python bench.py"
oc rsh $pod bash -c "TARGET_TYPE=direct MLFLOW_TRACKING_URI=http://169.63.180.173:5000 python bench.py"
