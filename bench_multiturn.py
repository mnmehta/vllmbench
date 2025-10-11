import os
import json
import re
import shlex
import subprocess
import sys
from typing import Dict

import hydra
import mlflow
from omegaconf import DictConfig, OmegaConf


MULTITURN_METRICS = {
    "runtime_sec": r"runtime_sec\s*=\s*([\d\.]+)",
    "requests_per_sec": r"requests_per_sec\s*=\s*([\d\.]+)",
}


def _run_in_pod(namespace: str, pod: str, workdir: str, args: list[str]) -> str:
    cmd = [
        "oc",
        "rsh",
        "-n",
        namespace,
        pod,
        "bash",
        "-lc",
        f"cd {shlex.quote(workdir)} && " + " ".join(shlex.quote(a) for a in args),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed in pod {pod}: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result.stdout


def _coerce_number_strings(obj):
    # Recursively convert numeric-looking strings to int/float for known keys
    if isinstance(obj, dict):
        coerced = {}
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                coerced[k] = _coerce_number_strings(v)
                continue
            if isinstance(v, str):
                s = v.strip()
                if s.replace(".", "", 1).isdigit() or (s.startswith("-") and s[1:].replace(".", "", 1).isdigit()):
                    # choose int if no dot, else float
                    coerced[k] = int(s) if "." not in s else float(s)
                    continue
            coerced[k] = v
        return coerced
    if isinstance(obj, list):
        return [_coerce_number_strings(x) for x in obj]
    return obj


def _oc_cp_to_pod(namespace: str, pod: str, local_path: str, remote_path: str, container: str | None = None) -> None:
    cmd = [
        "oc",
        "-n",
        namespace,
        "cp",
        local_path,
        f"{pod}:{remote_path}",
    ]
    if container:
        cmd.extend(["-c", container])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"oc cp failed: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )

@hydra.main(config_path="conf", config_name="default", version_base=None)
def main(cfg: DictConfig) -> None:
    # MLflow setup
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)

    # Resolve experiment name
    experiment_name = cfg.multiturn.experiment_name
    if isinstance(experiment_name, str):
        experiment_name = OmegaConf.to_container(cfg, resolve=True)["multiturn"]["experiment_name"]  # type: ignore[index]
    mlflow.set_experiment(str(experiment_name))

    namespace = cfg.multiturn.namespace
    pod_name = cfg.multiturn.pod_name
    workdir = cfg.multiturn.workdir

    # Write generated input JSON to /tmp (inside the pod we'll reference the same path)
    generated_input_path = cfg.multiturn.generated_input_path
    input_payload_raw = OmegaConf.to_container(cfg.multiturn.input, resolve=True)  # type: ignore[arg-type]
    input_payload = _coerce_number_strings(input_payload_raw)
    # Save locally (host) for logging artifact and then copy into pod
    host_tmp_path = "/tmp/multiturn_input.json"
    with open(host_tmp_path, "w") as f:
        json.dump(input_payload, f, indent=2)

    # Build command, mirroring provided example
    cmd = [
        "python3",
        "benchmark_serving_multi_turn.py",
        "--u",
        cfg.multiturn.url,
        "-m",
        cfg.run.model,
        "--input-file",
        generated_input_path,
        "--num-clients",
        str(cfg.multiturn.num_clients),
        "--max-active-conversations",
        str(cfg.multiturn.max_active_conversations),
        "--request-rate",
        str(cfg.multiturn.request_rate),
    ]

    with mlflow.start_run(run_name="multiturn"):
        # Log params
        mlflow.log_param("framework", cfg.run.framework)
        mlflow.log_param("model", cfg.run.model)
        mlflow.log_param("pod", pod_name)
        mlflow.log_param("namespace", namespace)
        mlflow.log_param("workdir", workdir)
        mlflow.log_param("url", cfg.multiturn.url)
        mlflow.log_param("num_clients", cfg.multiturn.num_clients)
        mlflow.log_param("max_active_conversations", cfg.multiturn.max_active_conversations)
        mlflow.log_param("request_rate", cfg.multiturn.request_rate)
        # Log this script and conf directory as artifacts
        script_file = os.path.abspath(__file__)
        try:
            mlflow.log_artifact(script_file, artifact_path="source_code")
        except Exception:
            pass
        try:
            script_dir = os.path.dirname(script_file)
            conf_candidates = [
                os.path.join(script_dir, "conf"),
                os.path.abspath("conf"),
            ]
            for conf_dir in conf_candidates:
                if os.path.isdir(conf_dir):
                    try:
                        mlflow.log_artifacts(conf_dir, artifact_path="conf")
                    except Exception:
                        pass
                    break
        except Exception:
            pass

        # Log command string
        command_str = "oc rsh -n {} {} bash -lc {}".format(
            namespace,
            pod_name,
            shlex.quote("cd {} && {}".format(workdir, " ".join(shlex.quote(a) for a in cmd))),
        )
        mlflow.log_param("benchmark_cmd", command_str)

        # Copy input file into the pod at the generated path
        _oc_cp_to_pod(namespace, pod_name, host_tmp_path, generated_input_path, container="vllm")

        # Execute
        output = _run_in_pod(namespace, pod_name, workdir, cmd)
        print(output)

        # Parse metrics
        metrics: Dict[str, float] = {}
        for key, pattern in MULTITURN_METRICS.items():
            m = re.search(pattern, output)
            if m:
                metrics[key] = float(m.group(1))

        # Parse statistics summary table at the end
        # Primary pattern: full table with all columns
        full_row_pattern = re.compile(
            r"^(?P<name>[A-Za-z0-9_]+)\s+"
            r"(?P<count>[\d\.]+)\s+"
            r"(?P<mean>[\d\.]+)\s+"
            r"(?P<std>[\d\.]+)\s+"
            r"(?P<min>[\d\.]+)\s+"
            r"(?P<p25>[\d\.]+)\s+"
            r"(?P<p50>[\d\.]+)\s+"
            r"(?P<p75>[\d\.]+)\s+"
            r"(?P<p90>[\d\.]+)\s+"
            r"(?P<max>[\d\.]+)\s*$",
            re.MULTILINE,
        )
        any_full = False
        for match in full_row_pattern.finditer(output):
            any_full = True
            name = match.group("name")
            for col in [
                "count",
                "mean",
                "std",
                "min",
                "p25",
                "p50",
                "p75",
                "p90",
                "max",
            ]:
                try:
                    value = float(match.group(col))
                    metrics[f"{name}_{col}"] = value
                except Exception:
                    pass

        # Fallback pattern: pandas-style truncated header with ellipses
        if not any_full:
            truncated_row_pattern = re.compile(
                r"^(?P<name>[A-Za-z0-9_]+)\s+"
                r"(?P<count>[\d\.]+)\s+"
                r"(?P<mean>[\d\.]+)\s+"
                r"(?P<std>[\d\.]+)\s+\.\.\.\s+"
                r"(?P<p75>[\d\.]+)\s+"
                r"(?P<p90>[\d\.]+)\s+"
                r"(?P<max>[\d\.]+)\s*$",
                re.MULTILINE,
            )
            for match in truncated_row_pattern.finditer(output):
                name = match.group("name")
                for col in [
                    "count",
                    "mean",
                    "std",
                    "p75",
                    "p90",
                    "max",
                ]:
                    try:
                        value = float(match.group(col))
                        metrics[f"{name}_{col}"] = value
                    except Exception:
                        pass

        for k, v in metrics.items():
            mlflow.log_metric(k, v)

        # Log generated input JSON as artifact
        try:
            mlflow.log_text(json.dumps(input_payload, indent=2) + "\n", artifact_file="multiturn_input.json")
        except Exception:
            pass
        # Log full benchmark output
        try:
            mlflow.log_text(output, artifact_file="multiturn_output.txt")
        except Exception:
            pass


if __name__ == "__main__":
    main()


