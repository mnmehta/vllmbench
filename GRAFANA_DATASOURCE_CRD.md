# Grafana Prometheus DataSource - CRD Configuration

## Overview

The Prometheus datasource is configured using the Grafana Operator's `GrafanaDataSource` CRD instead of manual UI configuration. This approach:
- Avoids TLS certificate errors in the UI
- Enables GitOps-style declarative configuration
- Automatically syncs to the Grafana instance

## Current Configuration

**Resource:** `prometheus-datasource` (GrafanaDataSource CRD)
**Namespace:** `openshift-operators`
**Status:** Successfully applied and verified

### Key Settings

- **Name:** Prometheus (OpenShift Monitoring)
- **Type:** prometheus
- **URL:** https://thanos-querier-openshift-monitoring.apps.psap-aus-h200.ibm.rhperfscale.org
- **Access Mode:** proxy
- **Default Datasource:** Yes
- **TLS Skip Verify:** Enabled (required for certificate issues)
- **Authentication:** Bearer token via custom HTTP header

### Authentication Details

- **Header Name:** `Authorization`
- **Header Value:** `Bearer <token>` (auto-generated 10-year token)
- **Service Account:** `grafana-datasource` in `openshift-operators` namespace
- **Permissions:** `cluster-monitoring-view` (read-only)

## Verification

The datasource was verified with:

1. **Health Check:**
   ```json
   {
     "status": "OK",
     "message": "Successfully queried the Prometheus API.",
     "details": {
       "application": "Prometheus",
       "features": {"rulerApiEnabled": false}
     }
   }
   ```

2. **Live Query Test:**
   - Query: `up{namespace="llm-d-bench"}`
   - Results: Successfully retrieved metrics from 9 pods (1 EPP + 8 vLLM decode pods)
   - All pods reporting `up=1` (healthy)

## Files

- **CRD Manifest:** `/home/michey/llmd_aug2025/vllmbench/grafana-prometheus-datasource.yaml`
- **Setup Script:** `/home/michey/llmd_aug2025/vllmbench/grafana_cluster_setup.sh`

## Managing the DataSource

### View Current Configuration
```bash
oc get grafanadatasource prometheus-datasource -n openshift-operators -o yaml
```

### Check Status
```bash
oc get grafanadatasource prometheus-datasource -n openshift-operators
```

### Update Configuration
Edit `grafana-prometheus-datasource.yaml` and apply:
```bash
oc apply -f grafana-prometheus-datasource.yaml
```

### Delete DataSource
```bash
oc delete grafanadatasource prometheus-datasource -n openshift-operators
```

### Regenerate Token
If the bearer token expires or is compromised:
```bash
# Generate new token
TOKEN=$(oc create token grafana-datasource -n openshift-operators --duration=87600h)

# Update the datasource YAML with new token
# Edit grafana-prometheus-datasource.yaml, replace the token in secureJsonData.httpHeaderValue1

# Apply the update
oc apply -f grafana-prometheus-datasource.yaml
```

## Using the DataSource in Grafana

The datasource "Prometheus (OpenShift Monitoring)" is now available in Grafana and set as the default.

### Example Queries for vLLM Metrics

#### GPU Utilization
```promql
DCGM_FI_DEV_GPU_UTIL{namespace="llm-d-bench"}
```

#### vLLM Request Rate
```promql
rate(vllm_request_success_total{namespace="llm-d-bench"}[5m])
```

#### Pod Health Status
```promql
up{namespace="llm-d-bench"}
```

#### Container Memory Usage
```promql
container_memory_usage_bytes{namespace="llm-d-bench",container="vllm"}
```

#### Request Latency (95th percentile)
```promql
histogram_quantile(0.95, rate(vllm_request_duration_seconds_bucket{namespace="llm-d-bench"}[5m]))
```

## Troubleshooting

### DataSource Not Showing in Grafana UI

Check if the operator synced it:
```bash
oc get grafanadatasource prometheus-datasource -n openshift-operators -o jsonpath='{.status.conditions[0].message}'
```

Expected output: `Datasource was successfully applied to 1 instances`

### Query Errors

Test the connection manually:
```bash
TOKEN=$(oc create token grafana-datasource -n openshift-operators --duration=1h)
curl -H "Authorization: Bearer ${TOKEN}" \
  "https://thanos-querier-openshift-monitoring.apps.psap-aus-h200.ibm.rhperfscale.org/api/v1/query?query=up"
```

### Check Grafana Logs

```bash
oc logs -n openshift-operators deployment/grafana-a-deployment --tail=50
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Grafana UI                              │
│          (grafana-route-openshift-operators...)              │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ Uses datasource
                       ▼
┌─────────────────────────────────────────────────────────────┐
│         GrafanaDataSource CRD                                │
│         prometheus-datasource                                │
│                                                              │
│  - URL: https://thanos-querier-openshift-monitoring...      │
│  - Auth: Bearer token (from service account)                │
│  - TLS Skip Verify: true                                    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ HTTP GET with Authorization header
                       ▼
┌─────────────────────────────────────────────────────────────┐
│         Thanos Querier (Prometheus)                          │
│         openshift-monitoring namespace                       │
│                                                              │
│  Aggregates metrics from:                                   │
│  - User workload monitoring (llm-d-bench namespace)         │
│  - Cluster monitoring                                       │
└─────────────────────────────────────────────────────────────┘
```

## Security Notes

- Service account token valid for 10 years (expires 2036)
- Read-only access via `cluster-monitoring-view` role
- Token is stored securely in Kubernetes secret (managed by Grafana Operator)
- External route uses proper TLS certificates from OpenShift
