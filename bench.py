import subprocess
import re
import mlflow
import sys
import os

from typing import Any, Dict

import hydra
from omegaconf import DictConfig, OmegaConf
import shlex
import tempfile


# Regex patterns to extract metrics
METRIC_PATTERNS = {
    "successful_requests": r"Successful requests:\s+(\d+)",
    "benchmark_duration_s": r"Benchmark duration \(s\):\s+([\d\.]+)",
    "total_input_tokens": r"Total input tokens:\s+(\d+)",
    "total_generated_tokens": r"Total generated tokens:\s+(\d+)",
    "request_throughput": r"Request throughput \(req/s\):\s+([\d\.]+)",
    "output_token_throughput": r"Output token throughput \(tok/s\):\s+([\d\.]+)",
    "total_token_throughput": r"Total Token throughput \(tok/s\):\s+([\d\.]+)",
    "mean_ttft": r"Mean TTFT \(ms\):\s+([\d\.]+)",
    "median_ttft": r"Median TTFT \(ms\):\s+([\d\.]+)",
    "p99_ttft": r"P99 TTFT \(ms\):\s+([\d\.]+)",
    "mean_tpot": r"Mean TPOT \(ms\):\s+([\d\.]+)",
    "median_tpot": r"Median TPOT \(ms\):\s+([\d\.]+)",
    "p99_tpot": r"P99 TPOT \(ms\):\s+([\d\.]+)",
    "mean_itl": r"Mean ITL \(ms\):\s+([\d\.]+)",
    "median_itl": r"Median ITL \(ms\):\s+([\d\.]+)",
    "p99_itl": r"P99 ITL \(ms\):\s+([\d\.]+)",
}


def _resolve_target(cfg: DictConfig) -> str:
    # Allow env overrides for compatibility
    env_target_type = os.environ.get("TARGET_TYPE")
    env_target = os.environ.get("TARGET")

    target_type = (env_target_type or cfg.target_type or "").lower()
    target = env_target or (cfg.target or "")

    if not target:
        if target_type == "gateway":
            target = "http://infra-inference-scheduling-inference-gateway-istio"
        elif target_type == "direct":
            target = "http://10.130.1.253:8000"
        else:
            print(f"Unknown TARGET_TYPE: {target_type!r}")
            sys.exit(1)

    return target


@hydra.main(config_path="conf", config_name="config", version_base=None)
def main(cfg: DictConfig) -> None:
    # Keep working directory unchanged (also set in conf)
    # Configure MLflow tracking URI if provided via env
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)

    # Resolve experiment name (supports interpolation from config)
    experiment_name = cfg.experiment_name
    if isinstance(experiment_name, str):
        # Interpolate omegaconf variables if present
        experiment_name = OmegaConf.to_container(cfg, resolve=True)["experiment_name"]  # type: ignore[index]
    mlflow.set_experiment(str(experiment_name))

    # Determine target
    target_type = (os.environ.get("TARGET_TYPE") or cfg.target_type).lower()
    target = _resolve_target(cfg)

    # Determine this script's filename
    script_file = os.path.abspath(__file__)

    seed = 12345678
    for concurrency in cfg.concurrencies:
        num_prompts = cfg.queries_per_user * concurrency

        print(
            f"\n===== {cfg.framework} - RUNNING {cfg.model} FOR {num_prompts} PROMPTS WITH {concurrency} CONCURRENCY {target_type} TARGET =====\n"
        )

        name = f"{target_type}_conc{concurrency}"
        with mlflow.start_run(run_name=name):
            # Log parameters
            mlflow.log_param("framework", cfg.framework)
            mlflow.log_param("model", cfg.model)
            mlflow.log_param("input_len", cfg.input_len)
            mlflow.log_param("output_len", cfg.output_len)
            mlflow.log_param("concurrency", concurrency)
            # Do this so I can sort by concurrency in the UI with numeric order
            mlflow.log_metric("concurrency", concurrency)
            mlflow.log_param("num_prompts", num_prompts)
            mlflow.log_param("queries_per_user", cfg.queries_per_user)
            mlflow.log_param("target_type", target_type)
            mlflow.log_param("target", target)

            # Log this script as an artifact
            mlflow.log_artifact(script_file, artifact_path="source_code")

            # Run the benchmark via subprocess
            cmd = [
                "python",
                "vllm-benchmark/benchmarks/benchmark_serving.py",
                "--model",
                cfg.model,
                "--base-url",
                target,
                "--dataset-name",
                "random",
                "--random-input-len",
                str(cfg.input_len),
                "--random-output-len",
                str(cfg.output_len),
                "--max-concurrency",
                str(concurrency),
                "--num-prompts",
                str(num_prompts),
                "--seed",
                str(seed),
                "--ignore-eos",
            ]

            # Record the exact command used
            command_str = " ".join(shlex.quote(part) for part in cmd)
            mlflow.log_param("benchmark_cmd", command_str)
            try:
                mlflow.log_text(command_str + "\n", artifact_file="benchmark_cmd.txt")
            except Exception:
                with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmpf:
                    tmpf.write(command_str + "\n")
                    tmp_path = tmpf.name
                try:
                    mlflow.log_artifact(tmp_path)
                finally:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
            seed += 1

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                output = result.stdout
                print(output)
            except subprocess.CalledProcessError as e:
                print("Error running vllm bench:", e)
                print(e.stdout)
                print(e.stderr)
                continue

            # Parse metrics
            metrics: Dict[str, float] = {}
            for key, pattern in METRIC_PATTERNS.items():
                match = re.search(pattern, output)
                if match:
                    metrics[key] = float(match.group(1))

            # Log metrics to MLflow
            for metric_name, value in metrics.items():
                mlflow.log_metric(metric_name, value)


if __name__ == "__main__":
    main()

