#! /bin/bash
NAMESPACE=llm-d-inference-scheduler envsubst < pushgateway.yaml | oc apply -n "$NAMESPACE" -f -