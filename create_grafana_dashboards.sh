#!/bin/bash

# Create Grafana Dashboards via CRD
# This script creates GrafanaDashboard resources for all LLM-D and Gateway API dashboards

set -e

# Color output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_header() {
    echo -e "${BLUE}==================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}==================================================${NC}"
}

NAMESPACE="openshift-operators"
OUTPUT_DIR="/home/michey/llmd_aug2025/vllmbench/grafana-dashboards"

mkdir -p "$OUTPUT_DIR"

print_header "Creating Grafana Dashboard CRDs"
echo ""

# Dashboard 1: LLM-D vLLM Overview
print_info "Creating dashboard: LLM-D vLLM Overview..."
DASHBOARD_JSON=$(cat /tmp/llm-d/docs/monitoring/grafana/dashboards/llm-d-vllm-overview.json | jq -c .)
cat > "$OUTPUT_DIR/llm-d-vllm-overview.yaml" << EOF
apiVersion: grafana.integreatly.org/v1beta1
kind: GrafanaDashboard
metadata:
  name: llm-d-vllm-overview
  namespace: $NAMESPACE
spec:
  instanceSelector:
    matchLabels:
      dashboards: "grafana-a"
  json: |
$(echo "$DASHBOARD_JSON" | jq . | sed 's/^/    /')
EOF

# Dashboard 2: LLM-D Diagnostic Drilldown
print_info "Creating dashboard: LLM-D Diagnostic Drilldown..."
DASHBOARD_JSON=$(cat /tmp/llm-d/docs/monitoring/grafana/dashboards/llm-d-diagnostic-drilldown-dashboard.json | jq -c .)
cat > "$OUTPUT_DIR/llm-d-diagnostic-drilldown.yaml" << EOF
apiVersion: grafana.integreatly.org/v1beta1
kind: GrafanaDashboard
metadata:
  name: llm-d-diagnostic-drilldown
  namespace: $NAMESPACE
spec:
  instanceSelector:
    matchLabels:
      dashboards: "grafana-a"
  json: |
$(echo "$DASHBOARD_JSON" | jq . | sed 's/^/    /')
EOF

# Dashboard 3: LLM-D Failure Saturation
print_info "Creating dashboard: LLM-D Failure Saturation..."
DASHBOARD_JSON=$(cat /tmp/llm-d/docs/monitoring/grafana/dashboards/llm-d-failure-saturation-dashboard.json | jq -c .)
cat > "$OUTPUT_DIR/llm-d-failure-saturation.yaml" << EOF
apiVersion: grafana.integreatly.org/v1beta1
kind: GrafanaDashboard
metadata:
  name: llm-d-failure-saturation
  namespace: $NAMESPACE
spec:
  instanceSelector:
    matchLabels:
      dashboards: "grafana-a"
  json: |
$(echo "$DASHBOARD_JSON" | jq . | sed 's/^/    /')
EOF

# Dashboard 4: Gateway API Inference Extension
print_info "Creating dashboard: Gateway API Inference Extension..."
DASHBOARD_JSON=$(cat /tmp/inference_gateway.json | jq -c .)
cat > "$OUTPUT_DIR/inference-gateway.yaml" << EOF
apiVersion: grafana.integreatly.org/v1beta1
kind: GrafanaDashboard
metadata:
  name: inference-gateway
  namespace: $NAMESPACE
spec:
  instanceSelector:
    matchLabels:
      dashboards: "grafana-a"
  datasources:
    - inputName: "DS_PROMETHEUS"
      datasourceName: "Prometheus (OpenShift Monitoring)"
  json: |
$(echo "$DASHBOARD_JSON" | jq . | sed 's/^/    /')
EOF

echo ""
print_info "Dashboard CRD manifests created in: $OUTPUT_DIR"
echo ""

# Apply all dashboards
print_header "Applying Dashboards to Cluster"
echo ""

for dashboard_file in "$OUTPUT_DIR"/*.yaml; do
    dashboard_name=$(basename "$dashboard_file" .yaml)
    print_info "Applying: $dashboard_name..."
    oc apply -f "$dashboard_file"
done

echo ""
print_header "Dashboard Creation Complete"
echo ""

# Check status
print_info "Checking dashboard sync status..."
sleep 3
oc get grafanadashboards -n $NAMESPACE

echo ""
print_info "Dashboards should now be available in Grafana UI"
GRAFANA_URL=$(oc get route grafana-route -n openshift-operators -o jsonpath='{.spec.host}')
echo "Grafana URL: https://$GRAFANA_URL"
echo ""
