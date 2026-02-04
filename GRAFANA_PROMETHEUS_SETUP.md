# Grafana Prometheus Data Source Setup

## Solution: Use External Route with Bearer Token

The TLS certificate error occurs because Grafana can't verify OpenShift's internal certificates. Here's the fix:

### Option 1: External Route (Recommended)

Use the external Thanos route which has proper certificates:

**Configuration:**

1. In Grafana, go to **Configuration** → **Data Sources** → **Add data source** → **Prometheus**

2. **Connection Settings:**
   ```
   URL: https://thanos-querier-openshift-monitoring.apps.psap-aus-h200.ibm.rhperfscale.org
   ```

3. **Authentication:**
   - Scroll down to **Custom HTTP Headers**
   - Click **+ Add header**
     - Header: `Authorization`
     - Value: `Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6Im1HZXdiRkI0N1pUVWwwN0p3bHpyaFJwcGdBZ25xU2NpblZreGwzSFpVc1UifQ.eyJhdWQiOlsiaHR0cHM6Ly9rdWJlcm5ldGVzLmRlZmF1bHQuc3ZjIl0sImV4cCI6MjA4NTU0ODg0MywiaWF0IjoxNzcwMTg4ODQzLCJpc3MiOiJodHRwczovL2t1YmVybmV0ZXMuZGVmYXVsdC5zdmMiLCJqdGkiOiI1MDdkNTdhYy0yY2NlLTQ4M2MtOWMxMi05ZWIwYjRmYjQ2YzUiLCJrdWJlcm5ldGVzLmlvIjp7Im5hbWVzcGFjZSI6Im9wZW5zaGlmdC1vcGVyYXRvcnMiLCJzZXJ2aWNlYWNjb3VudCI6eyJuYW1lIjoiZ3JhZmFuYS1kYXRhc291cmNlIiwidWlkIjoiMjVlZGFhN2MtODk4OC00ODA3LWFkNWQtNzZiZTE5YzM0MTQ4In19LCJuYmYiOjE3NzAxODg4NDMsInN1YiI6InN5c3RlbTpzZXJ2aWNlYWNjb3VudDpvcGVuc2hpZnQtb3BlcmF0b3JzOmdyYWZhbmEtZGF0YXNvdXJjZSJ9.oSdDbkaMauEeZsv4GEmBw2cM2dSKMt2b7dTHpkNYyB_GwpRHYmqkSLC4kBFHrTMuWiYvxNpaVl452ZQflKxjCSrsEY9GHUN8gdjPkqre2xSOgh7uo0H2vOAT_kVxc4SSHzIRB6KQ1DrSd1nhOnVM_gvO3DjzyZ-o3kOPxvgGXPz7W5aSqXE4epqSlch37KstdVrVuTBowbVKpBRoMlE4ScYmthgdSHjIEjh-wG0sfKdJkDLcfYXvGKNIZOOB31feVkndbntp7R54snD9GVpNQF0IcWcD3j0cnNAv0BZCBnY0PL98dqBQx_MhDMJX85KtxqPFy_aXufQaxOHvRK8btGLqEXbgN8VMxev2fUu_B9l33Cf6xKUAnpYkM0lP-u0u4Hjyi_pVZTqkT9FX6_K-3VhHFBeZ-LasWHXiExUWTYEDQ37hRg_tFJsSwCI7TvUH2UjUObIvHJL13pCUCBxmFHypwFIIvOi9G0zdGs3PCFfTHvKdlSjG900FaKpxqYTXZRhb_blfvjst1fn-80TVhXjPiBpu5J_fYzGklfJfDWjmLvNRDZUKwwWT1sSA7sz2SOcppMLVlKob1A1U_d_PQEakY68AGycLa8_FbyHiKwRL9e5A10JvRFOgibyyUd2eL47PJelSj0v_YNUcG841YedPkmarHTHZcdL50Tq8Mcw`

   (The entire token including "Bearer " prefix should be in the Value field)

4. **Additional Settings:**
   - Leave **Skip TLS Verify** OFF (external route has valid certs)
   - HTTP Method: `POST` (default)

5. Click **Save & Test**

You should see: ✅ **"Successfully queried the Prometheus API."**

---

### Option 2: Internal Service with TLS Skip (Alternative)

If you prefer to use the internal service URL:

**Configuration:**

1. **Connection Settings:**
   ```
   URL: https://thanos-querier.openshift-monitoring.svc.cluster.local:9091
   ```

2. **Authentication:**
   - Add Custom HTTP Header as in Option 1 (same token)

3. **TLS/SSL Settings:**
   - Enable **Skip TLS Verify** ✅

4. Click **Save & Test**

---

## Quick Copy-Paste Values

### External Route URL:
```
https://thanos-querier-openshift-monitoring.apps.psap-aus-h200.ibm.rhperfscale.org
```

### Bearer Token:
```
eyJhbGciOiJSUzI1NiIsImtpZCI6Im1HZXdiRkI0N1pUVWwwN0p3bHpyaFJwcGdBZ25xU2NpblZreGwzSFpVc1UifQ.eyJhdWQiOlsiaHR0cHM6Ly9rdWJlcm5ldGVzLmRlZmF1bHQuc3ZjIl0sImV4cCI6MjA4NTU0ODg0MywiaWF0IjoxNzcwMTg4ODQzLCJpc3MiOiJodHRwczovL2t1YmVybmV0ZXMuZGVmYXVsdC5zdmMiLCJqdGkiOiI1MDdkNTdhYy0yY2NlLTQ4M2MtOWMxMi05ZWIwYjRmYjQ2YzUiLCJrdWJlcm5ldGVzLmlvIjp7Im5hbWVzcGFjZSI6Im9wZW5zaGlmdC1vcGVyYXRvcnMiLCJzZXJ2aWNlYWNjb3VudCI6eyJuYW1lIjoiZ3JhZmFuYS1kYXRhc291cmNlIiwidWlkIjoiMjVlZGFhN2MtODk4OC00ODA3LWFkNWQtNzZiZTE5YzM0MTQ4In19LCJuYmYiOjE3NzAxODg4NDMsInN1YiI6InN5c3RlbTpzZXJ2aWNlYWNjb3VudDpvcGVuc2hpZnQtb3BlcmF0b3JzOmdyYWZhbmEtZGF0YXNvdXJjZSJ9.oSdDbkaMauEeZsv4GEmBw2cM2dSKMt2b7dTHpkNYyB_GwpRHYmqkSLC4kBFHrTMuWiYvxNpaVl452ZQflKxjCSrsEY9GHUN8gdjPkqre2xSOgh7uo0H2vOAT_kVxc4SSHzIRB6KQ1DrSd1nhOnVM_gvO3DjzyZ-o3kOPxvgGXPz7W5aSqXE4epqSlch37KstdVrVuTBowbVKpBRoMlE4ScYmthgdSHjIEjh-wG0sfKdJkDLcfYXvGKNIZOOB31feVkndbntp7R54snD9GVpNQF0IcWcD3j0cnNAv0BZCBnY0PL98dqBQx_MhDMJX85KtxqPFy_aXufQaxOHvRK8btGLqEXbgN8VMxev2fUu_B9l33Cf6xKUAnpYkM0lP-u0u4Hjyi_pVZTqkT9FX6_K-3VhHFBeZ-LasWHXiExUWTYEDQ37hRg_tFJsSwCI7TvUH2UjUObIvHJL13pCUCBxmFHypwFIIvOi9G0zdGs3PCFfTHvKdlSjG900FaKpxqYTXZRhb_blfvjst1fn-80TVhXjPiBpu5J_fYzGklfJfDWjmLvNRDZUKwwWT1sSA7sz2SOcppMLVlKob1A1U_d_PQEakY68AGycLa8_FbyHiKwRL9e5A10JvRFOgibyyUd2eL47PJelSj0v_YNUcG841YedPkmarHTHZcdL50Tq8Mcw
```

(Copy the entire token WITHOUT "Bearer " prefix - Grafana will add it automatically in custom headers)

---

## Viewing vLLM Metrics

Once the data source is configured, create a dashboard and use these queries:

### GPU Utilization:
```promql
DCGM_FI_DEV_GPU_UTIL{namespace="llm-d-bench"}
```

### vLLM Requests:
```promql
rate(vllm_request_success_total{namespace="llm-d-bench"}[5m])
```

### Pod CPU/Memory:
```promql
container_memory_usage_bytes{namespace="llm-d-bench",container="vllm"}
```

### Request Latency (if available):
```promql
histogram_quantile(0.95, rate(vllm_request_duration_seconds_bucket{namespace="llm-d-bench"}[5m]))
```

---

## Token Details

- **Service Account:** `grafana-datasource` in `openshift-operators` namespace
- **Permissions:** `cluster-monitoring-view` role
- **Validity:** 10 years (expires 2036)
- **Purpose:** Read-only access to Prometheus metrics

---

## Troubleshooting

### If you still get certificate errors:
1. Make sure you're using the **external route URL** (not the .svc.cluster.local URL)
2. Verify the Bearer token is correctly pasted in the Custom HTTP Headers section
3. The header name should be exactly: `Authorization`
4. The header value should start with: `Bearer ` (with a space after)

### If you get "unauthorized" errors:
- Check that the full token is copied correctly
- Verify the service account exists: `oc get sa grafana-datasource -n openshift-operators`

### Test the endpoint manually:
```bash
curl -H "Authorization: Bearer <your-token>" \
  https://thanos-querier-openshift-monitoring.apps.psap-aus-h200.ibm.rhperfscale.org/api/v1/query?query=up
```

You should get JSON response with metrics.
