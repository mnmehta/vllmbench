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


def _escape_label_value(value: str) -> str:
    # Prometheus exposition label escaping: backslash and double-quote
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _pushgateway_post(url: str, body: str) -> None:
    # Use curl to support -k for self-signed TLS (route edge)
    cmd = [
        "curl",
        "-s",
        "-S",
        "-k",
        "--data-binary",
        "@-",
        url,
    ]
    subprocess.run(cmd, input=body, text=True, check=True)


def _pushgateway_delete(url: str) -> None:
    cmd = [
        "curl",
        "-s",
        "-S",
        "-k",
        "-X",
        "DELETE",
        url,
    ]
    subprocess.run(cmd, check=True)


def _push_runconfig_metric(cfg: DictConfig) -> tuple[str, str, str] | None:
    """Push a runconfig gauge=1 with key parameters as labels to Pushgateway.

    Returns (pgw_base, job, instance) if pushed, for later deletion.
    """
    DEFAULT_PGW = "https://prometheus-pushgateway-llm-d-inference-scheduler.apps.psap-llmd-h200.ibm-rh-ai.rhperfscale.org"
    pgw_base = os.environ.get("PUSHGATEWAY_URL", DEFAULT_PGW).strip()

    job = os.environ.get("PUSHGATEWAY_JOB", "bench_multiturn").strip()
    instance = os.environ.get("PUSHGATEWAY_INSTANCE", os.uname().nodename).strip()

    # Collect labels from cfg
    labels: Dict[str, str] = {}
    try:
        labels["run_name"] = str(cfg.guidellm_multiturn.run_name)
        labels["framework"] = str(cfg.run.framework)
        labels["model"] = str(cfg.run.model)
        labels["namespace"] = str(cfg.guidellm_multiturn.namespace)
        labels["pod"] = str(cfg.guidellm_multiturn.pod_name)
        labels["profile"] = str(cfg.guidellm_multiturn.profile)
        labels["rate"] = str(cfg.guidellm_multiturn.rate)
        labels["max_requests"] = str(cfg.guidellm_multiturn.max_requests)
        labels["target"] = str(cfg.guidellm_multiturn.target)
        labels["workdir"] = str(cfg.guidellm_multiturn.workdir)
        labels["replicas"] = str(cfg.install.decode_replicas)
        # MLflow run URL (if tracking URI is HTTP)
        try:
            active = mlflow.active_run()
            if active is not None:
                tracking_uri = mlflow.get_tracking_uri() or ""
                if tracking_uri.startswith("http"):
                    base = tracking_uri.rstrip("/")
                    exp_id = active.info.experiment_id
                    run_id = active.info.run_id
                    labels["mlflow_url"] = f"{base}/#/experiments/{exp_id}/runs/{run_id}"
        except Exception:
            pass
        # Data mapping as a compact string
        data_map = OmegaConf.to_container(cfg.guidellm_multiturn.data, resolve=True)
        if isinstance(data_map, dict):
            labels["data"] = ",".join(f"{k}={v}" for k, v in data_map.items())
        else:
            labels["data"] = str(cfg.guidellm_multiturn.data)
    except Exception:
        pass

    # Build exposition line
    # runconfig{labelK="v",...} 1
    label_parts = [
        f"{k}=\"{_escape_label_value(v)}\"" for k, v in sorted(labels.items())
    ]
    line = f"runconfig{{{','.join(label_parts)}}} 1\n"

    url = f"{pgw_base.rstrip('/')}/metrics/job/{job}/instance/{instance}"
    try:
        _pushgateway_post(url, line)
        print(f"[pushgateway] pushed runconfig to {url}")
    except subprocess.CalledProcessError as e:
        print(f"[pushgateway] push failed: {e}")
        return None
    return (pgw_base, job, instance)


def _push_runconfig_delete(pgw_base: str, job: str, instance: str) -> None:
    url = f"{pgw_base.rstrip('/')}/metrics/job/{job}/instance/{instance}"
    try:
        _pushgateway_delete(url)
        print(f"[pushgateway] deleted runconfig at {url}")
    except subprocess.CalledProcessError as e:
        print(f"[pushgateway] delete failed: {e}")


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
        # Push runconfig metric at start (best-effort)
        pgw_info = _push_runconfig_metric(cfg)
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
        finally:
            # Ensure deletion of runconfig metric at end
            if pgw_info is not None:
                _push_runconfig_delete(*pgw_info)


if __name__ == "__main__":
    main()


