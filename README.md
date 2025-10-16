## vllmbench: Running benchmarks and installers

This directory contains scripts to install the test environment and run single-turn and multi-turn benchmarks against vLLM-based deployments, with MLflow logging.

### Prerequisites
- oc (OpenShift CLI) configured for the target cluster
- helmfile installed and authenticated for your cluster
- Python 3.10+ with required libraries (hydra, omegaconf, mlflow)
- MLflow tracking server URL (optional but recommended)

You can override Hydra configuration directly on the command line via `group.option=value` syntax. See `conf/` for base configs.

### install_llmd.py
Installs or updates the inference stack using helmfile and waits for readiness.

Examples:
```bash
python install_llmd.py --config-name default
python install_llmd.py --config-name llama70b
python install_llmd.py --config-name llama70b_precise

# Override values
python install_llmd.py --config-name default install.well_lit_path=guides/inference-scheduling
python install_llmd.py --config-name default install.decode_replicas=8
```

### bench.py (single-turn benchmark)
Runs the vLLM single-turn `benchmark_serving.py` via `oc rsh`, logging results to MLflow.

Examples:
```bash
MLFLOW_TRACKING_URI=http://<mlflow-host>:5000 \
python bench.py --config-name default \
  run.model=Qwen/Qwen3-0.6B \
  run.experiment_name=single_turn_test

# Target overrides
python bench.py --config-name llama70b run.target_type=gateway
python bench.py --config-name llama70b run.target_type=direct run.target=http://10.0.0.1:8000
```

### bench_multiturn.py (multi-turn benchmark driver)
Runs the vLLM multi-turn benchmark `benchmark_serving_multi_turn.py` inside a vLLM pod via `oc rsh`. It generates a multi-turn input JSON and logs metrics to MLflow.

Key options come from the `multiturn` config group in `conf/default.yaml`, including `url`, `num_clients`, `max_active_conversations`, `request_rate`, and `seed`.

Examples:
```bash
MLFLOW_TRACKING_URI=http://<mlflow-host>:5000 \
python bench_multiturn.py --config-name default \
  install.decode_replicas=8 \
  run.model=Qwen/Qwen3-0.6B \
  multiturn.max_active_conversations=512 \
  multiturn.input.num_conversations=512 \
  multiturn.seed=123456
```

### bench_multiturn.sh (multi-turn sweep)
Shell wrapper to install configurations and sweep multiple values, passing `multiturn.seed` and incrementing it per run. Edit the arrays near the top to choose configs and labels.

Usage:
```bash
bash bench_multiturn.sh
```

Notes:
- Set `experiment_name` and `run_name` at the top of the script.
- The script initializes `seed=999999` and increments it after each call so every run uses a unique seed.

### bench_multiturn_test.sh (focused test loop)
Smaller variant for targeted iterations on a single configuration, also passing and incrementing `multiturn.seed`.

Usage:
```bash
bash bench_multiturn_test.sh
```

### run_bench.sh (example single-turn pipeline)
Convenience script that alternates installs and single-turn runs with different configs.

Usage:
```bash
bash run_bench.sh
```

### Common Hydra overrides
- `install.decode_replicas=<int>`: set model service replica count
- `run.model=<hf_repo_or_path>`: choose model
- `run.experiment_name=<name>` / `multiturn.experiment_name=<name>`: MLflow experiment
- `multiturn.input.prompt_input.num_turns.min=<n>` and `.max=<n>`: set turns
- `multiturn.max_active_conversations=<n>`, `multiturn.num_clients=<n>`, `multiturn.request_rate=<float>`
- `multiturn.seed=<int>`: control randomness for conversation generation and client behavior

### MLflow
Set `MLFLOW_TRACKING_URI` in the environment to log metrics and artifacts:
```bash
export MLFLOW_TRACKING_URI=http://<mlflow-host>:5000
```


