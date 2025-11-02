#! /bin/bash
# Use Mehul's Thanos scripting from https://github.com/openshift-psap/observability
git clone https://github.com/openshift-psap/observability.git
cd observability
cd central-query-plane
export NAMESPACE=llm-d-inference-scheduler
export DASHBOARD_FILE=../vllm-dcgm-complete-dashboard.json
# Login to https://us-east-1.console.aws.amazon.com/s3/buckets/psap-hf-models?bucketType=general&region=us-east-1&tab=objects# and create a new bucket called michey-llmd-metrics
./scripts/deploy.sh

cd ../cluster-ingestion-plane
export CLUSTER_NAME=psap-llmd-8xh200
export NAMESPACE=llm-d-inference-scheduler
./scripts/deploy.sh