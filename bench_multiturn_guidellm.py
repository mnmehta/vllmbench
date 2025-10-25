# Co-authored by Cursor

import os
import json
import shlex
import subprocess
from typing import Dict, List

import hydra
import mlflow
from omegaconf import DictConfig, OmegaConf


def _run_in_pod(namespace: str, pod: str, args: List[str]) -> str:
    cmd = [
        "oc",
        "rsh",
        "-n",
        namespace,
        pod,
        "bash",
        "-lc",
        " ".join(shlex.quote(a) for a in args),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed in pod {pod}: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result.stdout


# Text parsing removed; rely solely on benchmarks.json


def _oc_cp_from_pod(namespace: str, pod: str, remote_path: str, local_path: str) -> None:
    cmd = [
        "oc",
        "-n",
        namespace,
        "cp",
        f"{pod}:{remote_path}",
        local_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"oc cp (from pod) failed: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )


def _extract_metrics_from_benchmarks_json(data: dict) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    try:
        benches = data.get("benchmarks", [])
        if not benches:
            return metrics
        b0 = benches[0]
        # Duration
        dur = b0.get("duration")
        if isinstance(dur, (int, float)):
            metrics["duration_sec"] = float(dur)

        # Totals
        totals = b0.get("request_totals", {})
        for key in ("successful", "errored", "incomplete", "total"):
            val = totals.get(key)
            if isinstance(val, (int, float)):
                metrics[f"requests_{key}"] = float(val)

        m = b0.get("metrics", {})
        def get_stat(group: str, bucket: str, stat: str) -> float | None:
            try:
                return float(m[group][bucket][stat])
            except Exception:
                return None

        def get_percentile(group: str, bucket: str, perc: str) -> float | None:
            try:
                return float(m[group][bucket]["percentiles"][perc])
            except Exception:
                return None

        # Throughputs
        for group, prefix in [
            ("requests_per_second", "rps_total"),
            ("output_tokens_per_second", "out_tok_per_sec_total"),
            ("tokens_per_second", "tok_per_sec_total"),
        ]:
            v = get_stat(group, "total", "mean")
            if v is not None:
                metrics[f"{prefix}_mean"] = v
            v = get_stat(group, "total", "median")
            if v is not None:
                metrics[f"{prefix}_median"] = v
            v = get_percentile(group, "total", "p99")
            if v is not None:
                metrics[f"{prefix}_p99"] = v

        # Latencies
        for stat, suffix in [("mean", "mean"), ("median", "median"), ("p99", "p99")]:
            v = get_stat("request_latency", "total", stat)
            if v is not None:
                metrics[f"req_latency_{suffix}_s"] = v

        for group, name in [
            ("time_to_first_token_ms", "ttft_ms"),
            ("time_per_output_token_ms", "tpot_ms"),
            ("inter_token_latency_ms", "itl_ms"),
        ]:
            v = get_stat(group, "total", "mean")
            if v is not None:
                metrics[f"{name}_mean"] = v
            v = get_stat(group, "total", "median")
            if v is not None:
                metrics[f"{name}_median"] = v
            v = get_percentile(group, "total", "p99")
            if v is not None:
                metrics[f"{name}_p99"] = v

        # Request concurrency (mean)
        v = get_stat("request_concurrency", "total", "mean")
        if v is not None:
            metrics["request_concurrency_mean"] = v

        # Token counts totals
        for group, name in [
            ("prompt_token_count", "prompt_tokens_total_sum"),
            ("output_token_count", "output_tokens_total_sum"),
            ("total_token_count", "total_tokens_total_sum"),
        ]:
            try:
                v = float(m[group]["total"]["total_sum"])
                metrics[name] = v
            except Exception:
                pass

    except Exception:
        pass
    return metrics


# Multi-variant invocation removed; we run the known-good command only


@hydra.main(config_path="conf", config_name="default", version_base=None)
def main(cfg: DictConfig) -> None:
    # MLflow setup
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)

    # Resolve experiment name
    experiment_name = cfg.guidellm_multiturn.experiment_name
    if isinstance(experiment_name, str):
        experiment_name = OmegaConf.to_container(cfg, resolve=True)["guidellm_multiturn"]["experiment_name"]  # type: ignore[index]
    mlflow.set_experiment(str(experiment_name))

    namespace = cfg.guidellm_multiturn.namespace
    pod_name = cfg.guidellm_multiturn.pod_name

    # Build exact GuideLLM command as requested
    # Serialize guidellm_multiturn.data mapping into key=value CSV without mutation
    data_cfg = OmegaConf.to_container(cfg.guidellm_multiturn.data, resolve=True)
    if isinstance(data_cfg, dict):
        data_kv = ",".join(f"{k}={v}" for k, v in data_cfg.items())
    else:
        data_kv = str(cfg.guidellm_multiturn.data)

    cmd = [
        "guidellm",
        "benchmark",
        "run",
        "--profile",
        str(cfg.guidellm_multiturn.profile),
        "--rate",
        str(cfg.guidellm_multiturn.rate),
        "--data",
        data_kv,
        "--target",
        str(cfg.guidellm_multiturn.target),
        "--max-requests",
        str(cfg.guidellm_multiturn.max_requests),
    ]

    with mlflow.start_run(run_name=cfg.guidellm_multiturn.run_name):
        # Log params
        mlflow.log_param("framework", cfg.run.framework)
        mlflow.log_param("model", cfg.run.model)
        mlflow.log_param("pod", pod_name)
        mlflow.log_param("namespace", namespace)
        # Align logging with bench_multiturn.py
        mlflow.log_param("workdir", cfg.guidellm_multiturn.workdir)
        mlflow.log_param("profile", cfg.guidellm_multiturn.profile)
        mlflow.log_param("rate", cfg.guidellm_multiturn.rate)
        mlflow.log_param("data", data_kv)
        mlflow.log_param("max_requests", cfg.guidellm_multiturn.max_requests)
        # Log GAIE overrides list for traceability (log even if None)
        try:
            gaie_overrides_cfg = getattr(cfg.install, "gaie_helmfile_overrides", None)
            try:
                gaie_overrides_val = OmegaConf.to_container(gaie_overrides_cfg, resolve=True)  # type: ignore[arg-type]
            except Exception:
                gaie_overrides_val = gaie_overrides_cfg
            if isinstance(gaie_overrides_val, (list, tuple)):
                value_str = ",".join(str(x) for x in gaie_overrides_val)
            else:
                value_str = str(gaie_overrides_val)
            mlflow.log_param("gaie_helmfile_overrides", value_str)
        except Exception:
            mlflow.log_param("gaie_helmfile_overrides", "<error>")
        mlflow.log_param("well_lit_path", cfg.install.well_lit_path)
        mlflow.log_param("target", cfg.guidellm_multiturn.target)
        mlflow.log_param("replicas", cfg.install.decode_replicas)

        # Log command string
        cmd_str = " ".join(shlex.quote(a) for a in cmd)
        command_str = f"oc rsh -n {namespace} {pod_name} bash -lc {shlex.quote(cmd_str)}"
        mlflow.log_param("benchmark_cmd", command_str)
        mlflow.log_param("guidellm_cmd_variant", cmd_str)

        # Execute
        print("Running guidellm:", cmd_str)
        output = _run_in_pod(namespace, pod_name, cmd)
        print(output)

        # Copy and parse benchmarks.json from the pod
        remote_json = "/vllm-workspace/benchmarks.json"
        local_json = os.path.join(os.getcwd(), "benchmarks.json")
        parsed_data = None
        try:
            _oc_cp_from_pod(namespace, pod_name, remote_json, local_json)
        except Exception as e:
            print("Failed to copy benchmarks.json:", e)
            local_json = None

        # Parse JSON metrics (required)
        metrics: Dict[str, float] = {}
        if local_json and os.path.isfile(local_json):
            try:
                with open(local_json, "r") as f:
                    data = json.load(f)
                parsed_data = data
                metrics = _extract_metrics_from_benchmarks_json(data)
                mlflow.log_param("guidellm_metrics_source", "benchmarks.json")
                try:
                    mlflow.log_artifact(local_json, artifact_path="guidellm")
                except Exception:
                    pass
            except Exception as e:
                print("Error reading/parsing benchmarks.json:", e)
        if not metrics:
            raise RuntimeError("Failed to obtain metrics from benchmarks.json; aborting.")

        for k, v in metrics.items():
            mlflow.log_metric(k, v)
        mlflow.log_metric("guidellm_parsed_metrics_count", float(len(metrics)))

        # Log metadata values (non-numeric) as params when available
        if parsed_data:
            try:
                benches = parsed_data.get("benchmarks", [])
                if benches and isinstance(benches[0], dict):
                    run_id = benches[0].get("run_id")
                    if isinstance(run_id, str) and run_id:
                        mlflow.log_param("guidellm_run_id", run_id)
            except Exception:
                pass
        # No text fallback for run id

        # Log full output
        try:
            mlflow.log_text(output, artifact_file="guidellm_output.txt")
        except Exception:
            pass


if __name__ == "__main__":
    main()


