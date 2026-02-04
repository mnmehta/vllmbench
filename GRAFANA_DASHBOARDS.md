# Grafana Dashboards - LLM-D and Gateway API

## Overview

Four Grafana dashboards have been deployed to monitor your LLM-D vLLM deployment and Gateway API inference extension:

1. **llm-d vLLM Overview** - Performance and inference metrics
2. **llm-d Diagnostic Drill-Down** - Detailed diagnostic analysis
3. **llm-d Failure & Saturation Indicators** - Health and capacity monitoring
4. **Inference Gateway** - Gateway API inference extension metrics

All dashboards are configured via GrafanaDashboard CRDs and automatically synced to the Grafana instance.

## Dashboard Details

### 1. llm-d vLLM Overview
- **UID:** `777792e8-8560-4f16-b55e-d21bcec11712`
- **Tags:** inference, llm-d, overview, performance, vllm
- **Purpose:** High-level overview of vLLM performance and inference metrics
- **Direct URL:** `/d/777792e8-8560-4f16-b55e-d21bcec11712/llm-d-vllm-overview`

### 2. llm-d Diagnostic Drill-Down
- **UID:** `llm-d-diagnostic-drilldown`
- **Tags:** diagnostic, drilldown, llm-d, monitoring, vllm
- **Purpose:** Detailed diagnostic information for troubleshooting
- **Direct URL:** `/d/llm-d-diagnostic-drilldown/llm-d-diagnostic-drill-down`

### 3. llm-d Failure & Saturation Indicators
- **UID:** `llm-d-failure-saturation`
- **Tags:** failure, llm-d, monitoring, saturation, vllm
- **Purpose:** Monitor system health, failures, and resource saturation
- **Direct URL:** `/d/llm-d-failure-saturation/llm-d-failure-and-saturation-indicators`

### 4. Inference Gateway
- **UID:** `aeap3g4ujefb4b`
- **Tags:** None
- **Purpose:** Monitor Gateway API inference extension metrics
- **Direct URL:** `/d/aeap3g4ujefb4b/inference-gateway`
- **Source:** [kubernetes-sigs/gateway-api-inference-extension](https://github.com/kubernetes-sigs/gateway-api-inference-extension/blob/main/tools/dashboards/inference_gateway.json)

## Accessing Dashboards

**Grafana URL:** https://grafana-route-openshift-operators.apps.psap-aus-h200.ibm.rhperfscale.org

**Login Credentials:**
- Username: `root`
- Password: `start`

**Dashboard Location:**
All dashboards are in the "openshift-operators" folder.

## Dashboard Status

Check dashboard sync status:
```bash
oc get grafanadashboards -n openshift-operators
```

Expected output:
```
NAME                         NO MATCHING INSTANCES   LAST RESYNC   AGE
inference-gateway                                    ...           ...
llm-d-diagnostic-drilldown                           ...           ...
llm-d-failure-saturation                             ...           ...
llm-d-vllm-overview                                  ...           ...
```

All dashboards should show:
- **Status:** "Dashboard was successfully applied to 1 instances"
- **Synced:** True

## Files

### Dashboard CRD Manifests
Located in: `/home/michey/llmd_aug2025/vllmbench/grafana-dashboards/`

- `llm-d-vllm-overview.yaml`
- `llm-d-diagnostic-drilldown.yaml`
- `llm-d-failure-saturation.yaml`
- `inference-gateway.yaml`

### Source Dashboard JSONs
- LLM-D dashboards: `/tmp/llm-d/docs/monitoring/grafana/dashboards/`
- Inference Gateway: Downloaded from GitHub

### Scripts
- **Creation Script:** `/home/michey/llmd_aug2025/vllmbench/create_grafana_dashboards.sh`
  - Generates GrafanaDashboard CRDs from JSON files
  - Applies all dashboards to the cluster
  - Verifies sync status

## Managing Dashboards

### View All Dashboards
```bash
oc get grafanadashboards -n openshift-operators
```

### View Specific Dashboard
```bash
oc get grafanadashboard llm-d-vllm-overview -n openshift-operators -o yaml
```

### Update a Dashboard

1. Edit the JSON source file
2. Regenerate the CRD:
```bash
./create_grafana_dashboards.sh
```

Or manually:
```bash
oc apply -f grafana-dashboards/llm-d-vllm-overview.yaml
```

### Delete a Dashboard
```bash
oc delete grafanadashboard llm-d-vllm-overview -n openshift-operators
```

### Delete All Dashboards
```bash
oc delete grafanadashboards --all -n openshift-operators
```

## Dashboard Features

### Data Source Mapping
All dashboards are configured to use the auto-configured Prometheus datasource:
- **Datasource Name:** "Prometheus (OpenShift Monitoring)"
- **Type:** Prometheus
- **URL:** https://thanos-querier-openshift-monitoring.apps.psap-aus-h200.ibm.rhperfscale.org

The Inference Gateway dashboard has explicit datasource mapping:
```yaml
datasources:
  - inputName: "DS_PROMETHEUS"
    datasourceName: "Prometheus (OpenShift Monitoring)"
```

### Namespace Filtering
Dashboards are pre-configured to monitor the `llm-d-bench` namespace where your vLLM deployment is running.

## Key Metrics Monitored

### vLLM Metrics
- Request throughput (requests/sec)
- Request latency (p50, p95, p99)
- GPU utilization
- Memory usage
- Active requests
- Queue depth
- Batch size
- Token generation rate

### Gateway Metrics
- Inference request rate
- Request duration
- Backend pool health
- Route performance
- Error rates

### System Metrics
- Pod CPU/Memory usage
- Container restarts
- Network I/O
- Storage I/O

## Troubleshooting

### Dashboard Not Showing in Grafana UI

1. Check CRD status:
```bash
oc get grafanadashboard <dashboard-name> -n openshift-operators -o jsonpath='{.status.conditions[0].message}'
```

2. Check Grafana operator logs:
```bash
oc logs -n openshift-operators deployment/grafana-operator-controller-manager
```

3. Verify instance selector matches:
```bash
oc get grafana grafana-a -n openshift-operators -o jsonpath='{.metadata.labels}'
```

### No Data in Dashboard

1. Verify Prometheus datasource is working:
```bash
# Check datasource health via Grafana API
GRAFANA_URL=$(oc get route grafana-route -n openshift-operators -o jsonpath='{.spec.host}')
GRAFANA_USER=$(oc get secret grafana-a-admin-credentials -n openshift-operators -o jsonpath='{.data.GF_SECURITY_ADMIN_USER}' | base64 -d)
GRAFANA_PASS=$(oc get secret grafana-a-admin-credentials -n openshift-operators -o jsonpath='{.data.GF_SECURITY_ADMIN_PASSWORD}' | base64 -d)

curl -k -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
  "https://${GRAFANA_URL}/api/datasources/uid/8dcda25d-ecbf-4581-98aa-d34d98176a95/health"
```

2. Check if metrics are being collected:
```bash
# Test Prometheus query
curl -H "Authorization: Bearer $(oc create token grafana-datasource -n openshift-operators --duration=1h)" \
  "https://thanos-querier-openshift-monitoring.apps.psap-aus-h200.ibm.rhperfscale.org/api/v1/query?query=up{namespace=\"llm-d-bench\"}"
```

3. Verify PodMonitor is collecting vLLM metrics:
```bash
oc get podmonitor -n llm-d-bench
```

### Dashboard Shows "No matching instances"

The GrafanaDashboard instanceSelector doesn't match any Grafana instances. Check:
```bash
oc get grafana -n openshift-operators --show-labels
```

Ensure the Grafana instance has label `dashboards: "grafana-a"`.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Grafana UI                              │
│  Dashboards:                                                 │
│  - llm-d vLLM Overview                                       │
│  - llm-d Diagnostic Drill-Down                               │
│  - llm-d Failure & Saturation Indicators                     │
│  - Inference Gateway                                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ Reads from datasource
                       ▼
┌─────────────────────────────────────────────────────────────┐
│         GrafanaDataSource: prometheus-datasource             │
│         (Prometheus - OpenShift Monitoring)                  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ Queries via bearer token
                       ▼
┌─────────────────────────────────────────────────────────────┐
│         Thanos Querier (Prometheus)                          │
│         Aggregates metrics from:                             │
│         - User workload monitoring (llm-d-bench)             │
│         - Cluster monitoring                                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ Scrapes metrics
                       ▼
┌─────────────────────────────────────────────────────────────┐
│         llm-d-bench namespace                                │
│  - vLLM decode pods (PodMonitor)                             │
│  - Gateway API EPP (PodMonitor)                              │
│  - ServiceMonitor for model services                         │
└─────────────────────────────────────────────────────────────┘
```

## Related Documentation

- [GRAFANA_ACCESS.md](GRAFANA_ACCESS.md) - Grafana UI access credentials
- [GRAFANA_PROMETHEUS_SETUP.md](GRAFANA_PROMETHEUS_SETUP.md) - Prometheus datasource configuration
- [GRAFANA_DATASOURCE_CRD.md](GRAFANA_DATASOURCE_CRD.md) - Datasource CRD details
- [grafana_cluster_setup.sh](grafana_cluster_setup.sh) - Cluster setup script

## Sources

- **LLM-D Dashboards:** `/tmp/llm-d/docs/monitoring/grafana/dashboards/`
- **Inference Gateway Dashboard:** [kubernetes-sigs/gateway-api-inference-extension](https://github.com/kubernetes-sigs/gateway-api-inference-extension)
  - File: `tools/dashboards/inference_gateway.json`
  - Documentation: https://gateway-api-inference-extension.sigs.k8s.io/guides/metrics-and-observability/
