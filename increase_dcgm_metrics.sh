#!/usr/bin/env bash

set -euo pipefail

# Increase metrics collected by NVIDIA DCGM Exporter by layering a custom metrics CSV
# - Adds SM utilization and SM occupancy, plus a recommended broader set of profiling metrics
# - Creates/updates a ConfigMap with the extended CSV
# - Mounts it into the dcgm-exporter DaemonSet and points DCGM_EXPORTER_COLLECTORS to it
# - Triggers a rolling restart

# Requirements:
# - oc CLI logged into the cluster
# - Permissions to modify resources in the NVIDIA GPU Operator namespace

NS="${NS:-nvidia-gpu-operator}"
DS_NAME="${DS_NAME:-nvidia-dcgm-exporter}"
CM_NAME="${CM_NAME:-dcgm-exporter-custom-metrics}"

echo "Namespace:           $NS"
echo "DaemonSet:           $DS_NAME"
echo "ConfigMap (custom):  $CM_NAME"
echo ""

echo "Locating a running dcgm-exporter pod..."
DCGM_POD=$(oc get pods -n "$NS" -l app=nvidia-dcgm-exporter -o jsonpath='{.items[0].metadata.name}')
if [[ -z "${DCGM_POD:-}" ]]; then
  echo "ERROR: dcgm-exporter pod not found in namespace $NS" >&2
  exit 1
fi
echo "Using pod: $DCGM_POD"

TMP_DIR=$(mktemp -d)
BASE_CSV="$TMP_DIR/base.csv"
CUSTOM_CSV="$TMP_DIR/custom-metrics.csv"

echo "Fetching current metrics CSV from the dcgm-exporter image..."
oc exec -n "$NS" "$DCGM_POD" -- cat /etc/dcgm-exporter/dcp-metrics-included.csv > "$BASE_CSV"

cp "$BASE_CSV" "$CUSTOM_CSV"

add_metric() {
  local field_id="$1"; shift
  local type="$1"; shift
  local help_msg="$*"
  # If an UNCOMMENTED line exists, skip
  if grep -Eq "^[[:space:]]*${field_id}[[:space:]]*," "$CUSTOM_CSV"; then
    echo "- Already present: $field_id"
    return 0
  fi
  # If only a COMMENTED line exists, uncomment it in-place
  if grep -Eq "^[[:space:]]*#[[:space:]]*${field_id}[[:space:]]*," "$CUSTOM_CSV"; then
    sed -E -i "s/^[[:space:]]*#[[:space:]]*(${field_id}[[:space:]]*,)/\1/" "$CUSTOM_CSV"
    echo "~ Uncommented: $field_id"
    return 0
  fi
  # Otherwise append a new entry
  echo "$field_id, $type, $help_msg" >> "$CUSTOM_CSV"
  echo "+ Added: $field_id"
}

echo "Appending additional profiling metrics (SM util/occupancy and more)..."
# Minimum requested
add_metric DCGM_FI_PROF_SM_ACTIVE       gauge "SM active cycles ratio (SM utilization)."
add_metric DCGM_FI_PROF_SM_OCCUPANCY    gauge "Average SM occupancy (ratio)."

# Broader recommended set
add_metric DCGM_FI_PROF_DRAM_ACTIVE     gauge "DRAM active cycles ratio (memory controller utilization)."
add_metric DCGM_FI_PROF_PIPE_FP16_ACTIVE  gauge "FP16 pipe active cycles ratio."
add_metric DCGM_FI_PROF_PIPE_FP32_ACTIVE  gauge "FP32 pipe active cycles ratio."
add_metric DCGM_FI_PROF_PIPE_FP64_ACTIVE  gauge "FP64 pipe active cycles ratio."
add_metric DCGM_FI_PROF_PIPE_TENSOR_ACTIVE gauge "Tensor core active cycles ratio."
add_metric DCGM_FI_PROF_PCIE_TX_BYTES     counter "Total PCIe TX bytes via NVML (profiling)."
add_metric DCGM_FI_PROF_PCIE_RX_BYTES     counter "Total PCIe RX bytes via NVML (profiling)."

echo ""
echo "Creating/updating ConfigMap: $CM_NAME"
oc create configmap "$CM_NAME" \
  -n "$NS" \
  --from-file=custom-metrics.csv="$CUSTOM_CSV" \
  --dry-run=client -o yaml | oc apply -f -

echo "Ensuring the DaemonSet mounts the custom metrics CSV..."
# Mount the ConfigMap at /etc/dcgm-exporter/custom (directory) for simplicity
if ! oc get ds -n "$NS" "$DS_NAME" -o yaml | grep -q "name: dcgm-custom-metrics"; then
  oc set volume ds/"$DS_NAME" -n "$NS" \
    --add --type=configmap \
    --name=dcgm-custom-metrics \
    --configmap-name="$CM_NAME" \
    --mount-path=/etc/dcgm-exporter/custom \
    --read-only
else
  echo "- Volume dcgm-custom-metrics already present"
fi

echo "Pointing DCGM_EXPORTER_COLLECTORS to the custom CSV..."
oc set env ds/"$DS_NAME" -n "$NS" \
  DCGM_EXPORTER_COLLECTORS=/etc/dcgm-exporter/custom/custom-metrics.csv

echo "Restarting dcgm-exporter DaemonSet to pick up changes..."
oc rollout restart ds/"$DS_NAME" -n "$NS"
oc rollout status ds/"$DS_NAME" -n "$NS" --timeout=2m

echo ""
echo "Done. Verify the new metrics exist by checking any dcgm-exporter pod at :9400/metrics, e.g.:"
echo "  oc -n $NS port-forward ds/$DS_NAME 9400:9400 &"
echo "  curl -s http://localhost:9400/metrics | egrep 'DCGM_FI_PROF_SM_ACTIVE|DCGM_FI_PROF_SM_OCCUPANCY'"
echo ""
echo "If you use OpenShift cluster-monitoring, they will be scraped as DCGM_* series."


