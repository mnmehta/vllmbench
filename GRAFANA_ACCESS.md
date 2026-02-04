# Grafana Access Guide

## Accessing Grafana UI

Your Grafana instance is now accessible via HTTPS route.

### Grafana URL
```
https://grafana-route-openshift-operators.apps.psap-aus-h200.ibm.rhperfscale.org
```

### Login Credentials
```
Username: root
Password: start
```

## Quick Access

Open your browser and navigate to:
🔗 https://grafana-route-openshift-operators.apps.psap-aus-h200.ibm.rhperfscale.org

Then login with the credentials above.

## What's Available

- **Grafana Instance:** `grafana-a` in namespace `openshift-operators`
- **Version:** 12.3.0
- **Service Port:** 3000

## Next Steps: Configure Prometheus Data Source

Once logged in, you'll want to add Prometheus as a data source:

1. Click on **Configuration** (⚙️) → **Data Sources**
2. Click **Add data source**
3. Select **Prometheus**
4. Configure the Prometheus URL:
   - For OpenShift monitoring: `https://thanos-querier.openshift-monitoring.svc.cluster.local:9091`
   - You may need to configure authentication (bearer token)

### Get Service Account Token for Prometheus

To access OpenShift Prometheus/Thanos, you may need a token:

```bash
# Create a service account with monitoring permissions
oc create sa grafana-prometheus-reader -n openshift-operators

# Add cluster monitoring view role
oc adm policy add-cluster-role-to-user cluster-monitoring-view -z grafana-prometheus-reader -n openshift-operators

# Get the token
oc create token grafana-prometheus-reader -n openshift-operators --duration=87600h
```

Copy the token and use it in Grafana's Prometheus data source configuration under:
- **Auth** → Enable **Forward OAuth Identity**
- Or add it as a Bearer token in custom HTTP headers

## Viewing Metrics

For your MLPerf/vLLM deployment metrics:

1. After adding Prometheus data source
2. Create a new dashboard
3. Query metrics like:
   - `vllm_*` - vLLM specific metrics
   - `container_*` - Container metrics
   - Filter by namespace: `{namespace="llm-d-bench"}`

## Resources

- Grafana Instance: `oc get grafana grafana-a -n openshift-operators`
- Grafana Pods: `oc get pods -n openshift-operators | grep grafana`
- Grafana Service: `oc get svc grafana-a-service -n openshift-operators`
- Grafana Route: `oc get route grafana-route -n openshift-operators`

## Troubleshooting

If you can't access the URL:
```bash
# Check route status
oc get route grafana-route -n openshift-operators

# Check pod status
oc get pods -n openshift-operators | grep grafana

# View pod logs
oc logs -n openshift-operators deployment/grafana-a-deployment
```

## Change Password (Optional)

After first login, you may want to change the password:
1. Click on your profile (bottom left)
2. Go to **Preferences** → **Change Password**
