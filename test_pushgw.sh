#! /bin/bash
PGW=https://prometheus-pushgateway-llm-d-inference-scheduler.apps.psap-llmd-h200.ibm-rh-ai.rhperfscale.org
JOB=my_job
INSTANCE=$(hostname)

cat <<'EOF' \
| curl -s -S -k --data-binary @- "$PGW/metrics/job/$JOB/instance/$INSTANCE"
# TYPE my_app_requests_total counter
my_app_requests_total{status="200"} 123
my_app_requests_total{status="500"} 7
# TYPE my_app_latency_seconds summary
my_app_latency_seconds{quantile="0.5"} 0.045
my_app_latency_seconds{quantile="0.9"} 0.120
my_app_latency_seconds_sum 12.34
my_app_latency_seconds_count 300
my_run{name="my_run"} 1
EOF

sleep 60

cat <<'EOF' \
| curl -s -S -k --data-binary @- "$PGW/metrics/job/$JOB/instance/$INSTANCE"
# TYPE my_app_requests_total counter
my_app_requests_total{status="200"} 124
my_app_requests_total{status="500"} 8
# TYPE my_app_latency_seconds summary
my_app_latency_seconds{quantile="0.5"} 0.045
my_app_latency_seconds{quantile="0.9"} 0.120
my_app_latency_seconds_sum 15
my_app_latency_seconds_count 300
my_run{name="my_run2"} 1
EOF

sleep 120
curl -s -S -k -X DELETE "$PGW/metrics/job/my_job/instance/$(hostname)"
