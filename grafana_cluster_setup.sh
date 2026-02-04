#!/bin/bash

# Grafana Cluster Setup Script
# Documents all cluster changes made for Grafana access and monitoring

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}=================================================="
    echo -e "$1"
    echo -e "==================================================${NC}"
}

usage() {
    cat << EOF
Usage: $0 [command]

Commands:
  apply        Apply all Grafana cluster configurations (includes Prometheus datasource)
  delete       Remove all Grafana cluster configurations
  status       Show current status of Grafana resources
  dashboards   Show dashboard status and recreate if needed
  token        Generate a new service account token
  help         Show this help message

Examples:
  $0 apply    # Set up Grafana access with auto-configured Prometheus datasource
  $0 delete   # Remove all Grafana configurations
  $0 status   # Check current setup and datasource status
  $0 token    # Generate new token for Prometheus data source

What this script does:
  - Creates HTTPS route for Grafana UI access
  - Creates service account with cluster monitoring permissions
  - Generates long-lived bearer token (10 years)
  - Auto-configures Prometheus datasource via GrafanaDataSource CRD
  - Datasource connects to OpenShift Thanos Querier with bearer token auth

EOF
}

# Apply all configurations
apply_config() {
    print_header "Setting Up Grafana Cluster Access"
    echo ""

    # Step 1: Create Grafana Route
    print_info "Step 1: Creating HTTPS route for Grafana UI..."
    if oc get route grafana-route -n openshift-operators &>/dev/null; then
        print_warn "Route 'grafana-route' already exists"
    else
        oc create route edge grafana-route \
            --service=grafana-a-service \
            --port=3000 \
            -n openshift-operators
        print_info "✓ Route created successfully"
    fi
    echo ""

    # Step 2: Create Service Account for Prometheus Access
    print_info "Step 2: Creating service account for Prometheus data source..."
    if oc get sa grafana-datasource -n openshift-operators &>/dev/null; then
        print_warn "Service account 'grafana-datasource' already exists"
    else
        oc create sa grafana-datasource -n openshift-operators
        print_info "✓ Service account created"
    fi
    echo ""

    # Step 3: Grant Monitoring Permissions
    print_info "Step 3: Granting cluster-monitoring-view permissions..."
    if oc get clusterrolebinding -o json | grep -q "grafana-datasource.*cluster-monitoring-view" 2>/dev/null; then
        print_warn "Permissions already granted"
    else
        oc adm policy add-cluster-role-to-user cluster-monitoring-view \
            -z grafana-datasource \
            -n openshift-operators
        print_info "✓ Permissions granted"
    fi
    echo ""

    # Step 4: Generate Token
    print_info "Step 4: Generating service account token (valid for 10 years)..."
    TOKEN=$(oc create token grafana-datasource -n openshift-operators --duration=87600h)
    echo ""
    print_info "✓ Token generated successfully"
    echo ""

    # Step 5: Create Prometheus DataSource CRD
    print_info "Step 5: Creating Prometheus datasource via CRD..."
    cat > grafana-prometheus-datasource.yaml << EOF
apiVersion: grafana.integreatly.org/v1beta1
kind: GrafanaDatasource
metadata:
  name: prometheus-datasource
  namespace: openshift-operators
spec:
  instanceSelector:
    matchLabels:
      dashboards: "grafana-a"
  datasource:
    name: Prometheus (OpenShift Monitoring)
    type: prometheus
    access: proxy
    url: https://thanos-querier-openshift-monitoring.apps.psap-aus-h200.ibm.rhperfscale.org
    isDefault: true
    editable: false
    jsonData:
      httpHeaderName1: "Authorization"
      tlsSkipVerify: true
      timeInterval: "30s"
    secureJsonData:
      httpHeaderValue1: "Bearer ${TOKEN}"
EOF

    if oc get grafanadatasource prometheus-datasource -n openshift-operators &>/dev/null; then
        print_warn "GrafanaDataSource 'prometheus-datasource' already exists, updating..."
        oc apply -f grafana-prometheus-datasource.yaml
    else
        oc create -f grafana-prometheus-datasource.yaml
        print_info "✓ GrafanaDataSource created successfully"
    fi

    # Wait for datasource to sync
    sleep 3

    # Verify datasource health
    if DATASOURCE_STATUS=$(oc get grafanadatasource prometheus-datasource -n openshift-operators -o jsonpath='{.status.conditions[0].message}' 2>/dev/null); then
        print_info "✓ Datasource status: $DATASOURCE_STATUS"
    fi
    echo ""

    # Display Summary
    print_header "Setup Complete!"
    echo ""
    GRAFANA_URL=$(oc get route grafana-route -n openshift-operators -o jsonpath='{.spec.host}')
    GRAFANA_USER=$(oc get secret grafana-a-admin-credentials -n openshift-operators -o jsonpath='{.data.GF_SECURITY_ADMIN_USER}' | base64 -d)
    GRAFANA_PASS=$(oc get secret grafana-a-admin-credentials -n openshift-operators -o jsonpath='{.data.GF_SECURITY_ADMIN_PASSWORD}' | base64 -d)

    echo "Grafana UI:"
    echo "  URL:      https://$GRAFANA_URL"
    echo "  Username: $GRAFANA_USER"
    echo "  Password: $GRAFANA_PASS"
    echo ""
    echo "Prometheus Data Source:"
    echo "  Status:   ✓ Auto-configured via GrafanaDataSource CRD"
    echo "  Name:     Prometheus (OpenShift Monitoring)"
    echo "  URL:      https://thanos-querier-openshift-monitoring.apps.psap-aus-h200.ibm.rhperfscale.org"
    echo "  Auth:     Bearer token (auto-applied)"
    echo ""
    echo "Bearer Token (for reference):"
    echo "$TOKEN"
    echo ""
    print_info "Configuration details saved to: grafana_setup_output.txt"
    print_info "Datasource CRD saved to: grafana-prometheus-datasource.yaml"

    # Save to file
    cat > grafana_setup_output.txt << EOFOUT
Grafana Setup - $(date)
================================================

Grafana UI Access:
  URL:      https://$GRAFANA_URL
  Username: $GRAFANA_USER
  Password: $GRAFANA_PASS

Prometheus Data Source Configuration:
  URL: https://thanos-querier-openshift-monitoring.apps.psap-aus-h200.ibm.rhperfscale.org

  Custom HTTP Header:
    Header: Authorization
    Value:  Bearer $TOKEN

Token Details:
  Service Account: grafana-datasource
  Namespace: openshift-operators
  Permissions: cluster-monitoring-view (read-only)
  Validity: 10 years

Resources Created:
  1. Route: grafana-route (openshift-operators namespace)
  2. Service Account: grafana-datasource (openshift-operators namespace)
  3. ClusterRoleBinding: cluster-monitoring-view for grafana-datasource
  4. GrafanaDataSource: prometheus-datasource (auto-configured Prometheus)

Next Steps:
  1. Open Grafana UI: https://$GRAFANA_URL
  2. Login with credentials above
  3. Prometheus datasource "Prometheus (OpenShift Monitoring)" is already configured
  4. Create dashboards to monitor vLLM in llm-d-bench namespace
EOFOUT

    echo ""
}

# Delete all configurations
delete_config() {
    print_header "Removing Grafana Cluster Configurations"
    echo ""

    print_warn "This will remove:"
    echo "  - Grafana route (grafana-route)"
    echo "  - Service account (grafana-datasource)"
    echo "  - ClusterRoleBinding (cluster-monitoring-view for grafana-datasource)"
    echo "  - GrafanaDataSource (prometheus-datasource)"
    echo ""
    read -p "Are you sure you want to continue? (yes/no): " confirm

    if [ "$confirm" != "yes" ]; then
        print_info "Aborted"
        exit 0
    fi

    echo ""
    print_info "Removing GrafanaDataSource..."
    oc delete grafanadatasource prometheus-datasource -n openshift-operators 2>/dev/null || print_warn "GrafanaDataSource not found or already removed"

    print_info "Removing cluster role binding..."
    oc adm policy remove-cluster-role-from-user cluster-monitoring-view \
        -z grafana-datasource \
        -n openshift-operators 2>/dev/null || print_warn "Role binding not found or already removed"

    print_info "Removing service account..."
    oc delete sa grafana-datasource -n openshift-operators 2>/dev/null || print_warn "Service account not found or already removed"

    print_info "Removing route..."
    oc delete route grafana-route -n openshift-operators 2>/dev/null || print_warn "Route not found or already removed"

    echo ""
    print_info "✓ Cleanup complete"
    echo ""
    print_warn "Note: The Grafana instance itself (grafana-a) was NOT removed"
    print_warn "To remove Grafana completely, delete the Grafana custom resource"
}

# Show current status
show_status() {
    print_header "Grafana Cluster Configuration Status"
    echo ""

    print_info "Grafana Instance:"
    oc get grafana grafana-a -n openshift-operators 2>/dev/null || print_error "Grafana instance not found"
    echo ""

    print_info "Grafana Pods:"
    oc get pods -n openshift-operators | grep grafana || print_error "No Grafana pods found"
    echo ""

    print_info "Grafana Route:"
    oc get route grafana-route -n openshift-operators 2>/dev/null || print_warn "Route not created"
    echo ""

    print_info "Service Account:"
    oc get sa grafana-datasource -n openshift-operators 2>/dev/null || print_warn "Service account not created"
    echo ""

    print_info "Grafana Service:"
    oc get svc grafana-a-service -n openshift-operators 2>/dev/null || print_error "Grafana service not found"
    echo ""

    print_info "Prometheus DataSource:"
    if oc get grafanadatasource prometheus-datasource -n openshift-operators &>/dev/null; then
        oc get grafanadatasource prometheus-datasource -n openshift-operators
        echo ""
        DATASOURCE_STATUS=$(oc get grafanadatasource prometheus-datasource -n openshift-operators -o jsonpath='{.status.conditions[0].message}' 2>/dev/null)
        echo "Status: $DATASOURCE_STATUS"
    else
        print_warn "Prometheus datasource not created"
    fi
    echo ""

    if oc get route grafana-route -n openshift-operators &>/dev/null; then
        GRAFANA_URL=$(oc get route grafana-route -n openshift-operators -o jsonpath='{.spec.host}')
        echo "Access URL: https://$GRAFANA_URL"
    fi
    echo ""
}

# Generate new token
generate_token() {
    print_header "Generating New Service Account Token"
    echo ""

    if ! oc get sa grafana-datasource -n openshift-operators &>/dev/null; then
        print_error "Service account 'grafana-datasource' does not exist"
        print_info "Run '$0 apply' to create it first"
        exit 1
    fi

    print_info "Generating token (valid for 10 years)..."
    TOKEN=$(oc create token grafana-datasource -n openshift-operators --duration=87600h)
    echo ""
    print_info "✓ Token generated successfully"
    echo ""
    echo "Bearer Token:"
    echo "$TOKEN"
    echo ""
    print_info "Use this token in Grafana Prometheus data source:"
    echo "  Custom HTTP Header:"
    echo "    Header: Authorization"
    echo "    Value:  Bearer <token-above>"
    echo ""
}

# Show and manage dashboards
show_dashboards() {
    print_header "Grafana Dashboard Status"
    echo ""

    print_info "Checking GrafanaDashboard resources..."
    if oc get grafanadashboards -n openshift-operators &>/dev/null; then
        oc get grafanadashboards -n openshift-operators -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[0].message,SYNCED:.status.conditions[0].status,AGE:.metadata.creationTimestamp
        echo ""

        DASHBOARD_COUNT=$(oc get grafanadashboards -n openshift-operators --no-headers 2>/dev/null | wc -l)
        print_info "Total dashboards: $DASHBOARD_COUNT"
    else
        print_warn "No dashboards found"
        echo ""
        print_info "To create dashboards, run:"
        echo "  ./create_grafana_dashboards.sh"
        return
    fi
    echo ""

    print_info "Dashboard URLs:"
    GRAFANA_URL=$(oc get route grafana-route -n openshift-operators -o jsonpath='{.spec.host}' 2>/dev/null)
    if [ -n "$GRAFANA_URL" ]; then
        echo "  Grafana UI: https://$GRAFANA_URL"
        echo ""
        echo "Available dashboards:"
        echo "  - llm-d vLLM Overview"
        echo "  - llm-d Diagnostic Drill-Down"
        echo "  - llm-d Failure & Saturation Indicators"
        echo "  - Inference Gateway"
    else
        print_warn "Grafana route not found"
    fi
    echo ""

    read -p "Do you want to recreate all dashboards? (yes/no): " recreate
    if [ "$recreate" = "yes" ]; then
        if [ -f "./create_grafana_dashboards.sh" ]; then
            print_info "Recreating dashboards..."
            ./create_grafana_dashboards.sh
        else
            print_error "Dashboard creation script not found: ./create_grafana_dashboards.sh"
        fi
    fi
}

# Main logic
case "${1:-help}" in
    apply)
        apply_config
        ;;
    delete)
        delete_config
        ;;
    status)
        show_status
        ;;
    dashboards)
        show_dashboards
        ;;
    token)
        generate_token
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        print_error "Unknown command: $1"
        echo ""
        usage
        exit 1
        ;;
esac
