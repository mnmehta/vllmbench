# Co-authored by Cursor

import os
import ast
import json
import subprocess
import sys
from typing import List

import hydra
from omegaconf import DictConfig, ListConfig

DEFAULT_RELEASE_NAME_POSTFIX = "inference-scheduling"


def _run(cmd: List[str], cwd: str | None = None) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=cwd)


def _ensure_repo(repo_url: str, clone_dir: str) -> None:
    if not os.path.isdir(clone_dir):
        _run(["git", "clone", repo_url, clone_dir])


def _get_pods_with_label(namespace: str, label_selector: str) -> List[str]:
    result = subprocess.run(
        [
            "oc",
            "get",
            "pods",
            "-n",
            namespace,
            "-l",
            label_selector,
            "-o",
            "jsonpath={.items[*].metadata.name}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    names = result.stdout.strip().split()
    return [n for n in names if n]


def _wait_for_pods_deleted(namespace: str, label_selector: str, poll_seconds: int = 2) -> None:
    while True:
        try:
            pods = _get_pods_with_label(namespace, label_selector)
        except subprocess.CalledProcessError:
            pods = []
        if not pods:
            print("All previous labeled pods deleted")
            return
        print("Waiting for old pods to delete:", ", ".join(pods))
        subprocess.run(["sleep", str(poll_seconds)])


def _curl_completion_in_pod(namespace: str, pod: str, container: str, url: str, model: str) -> tuple[int, str, str]:
    payload = {
        "model": model,
        "prompt": "Hello, how can I assist you today?",
        "max_tokens": 20,
        "temperature": 0.7,
        "top_p": 0.9,
    }
    data = json.dumps(payload)
    cmd = [
        "oc",
        "rsh",
        "-n",
        namespace,
        "-c",
        container,
        pod,
        "curl",
        "-sS",
        "-X",
        "POST",
        url,
        "-H",
        "Content-Type: application/json",
        "-d",
        data,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def wait_until_ready(namespace: str, model: str, container: str = "vllm", label_selector: str = "llm-d.ai/inferenceServing=true") -> None:
    # Wait for pods to appear
    pods: List[str] = []
    while not pods:
        try:
            pods = _get_pods_with_label(namespace, label_selector)
        except subprocess.CalledProcessError:
            pods = []
        if not pods:
            print("No vLLM pods found yet; waiting...")
            subprocess.run(["sleep", "2"])  # simple delay

    # Check each pod locally via 127.0.0.1:8000
    for pod in pods:
        print(f"Checking local inference on pod: {pod}")
        while True:
            code, out, err = _curl_completion_in_pod(
                namespace,
                pod,
                container,
                "http://127.0.0.1:8000/v1/completions",
                model,
            )
            if code == 0 and "logprobs" in out:
                print(f"Pod {pod} local inference OK")
                break
            print(f"Pod {pod} not ready (code={code}); retrying...")
            subprocess.run(["sleep", "1"])  # backoff

    # After all pods pass, check gateway via any pod (use first)
    gw_url = f"http://infra-{os.environ.get('RELEASE_NAME_POSTFIX', DEFAULT_RELEASE_NAME_POSTFIX)}-inference-gateway-istio/v1/completions"
    first_pod = pods[0]
    print("Checking gateway readiness via pod:", first_pod)
    while True:
        code, out, err = _curl_completion_in_pod(
            namespace,
            first_pod,
            container,
            gw_url,
            model,
        )
        if code == 0 and "logprobs" in out:
            print("Gateway is ready")
            break
        print(f"Gateway not ready (code={code}); retrying...")
        subprocess.run(["sleep", "1"])  # backoff


@hydra.main(config_path="conf", config_name="default", version_base=None)
def main(cfg: DictConfig) -> None:
    release_name_postfix = os.environ.get("RELEASE_NAME_POSTFIX", DEFAULT_RELEASE_NAME_POSTFIX)
    os.environ["RELEASE_NAME_POSTFIX"] = release_name_postfix
    print(f"Using RELEASE_NAME_POSTFIX={release_name_postfix}")

    infra_release = f"infra-{release_name_postfix}"
    gaie_release = f"gaie-{release_name_postfix}"
    ms_release = f"ms-{release_name_postfix}"

    repo_url = cfg.install.repo_url
    llmd_dir = cfg.install.llmd_dir
    well_lit_path = cfg.install.well_lit_path
    helmfile_overrides_value = cfg.install.helmfile_overrides
    gaie_helmfile_overrides_value = getattr(cfg.install, "gaie_helmfile_overrides", None)
    namespace = cfg.install.namespace
    helmfile_path = cfg.install.helmfile_path
    destroy_first = bool(cfg.install.destroy_first)
    decode_replicas = int(getattr(cfg.install, "decode_replicas", 8))
    decode_tp = int(getattr(cfg.install, "decode_tp", 1))

    # Clone if missing
    _ensure_repo(repo_url, llmd_dir)

    work_dir = os.path.join(llmd_dir, well_lit_path)
    if not os.path.isdir(work_dir):
        print(f"Work directory not found: {work_dir}")
        sys.exit(1)

    # Ensure HuggingFace token secret exists (fixed name expected by charts)
    hf_secret = "llm-d-hf-token"
    hf_check = subprocess.run(
        ["kubectl", "-n", namespace, "get", "secret", hf_secret],
        capture_output=True,
        text=True,
    )
    if hf_check.returncode != 0:
        hf_token = os.environ.get("HF_TOKEN", "").strip()
        if not hf_token:
            print(f"ERROR: Secret {hf_secret} not found and HF_TOKEN env var not set.")
            print("Set HF_TOKEN and re-run, e.g.: export HF_TOKEN=hf_xxx")
            sys.exit(1)
        print(f"Creating secret {hf_secret} from HF_TOKEN...")
        _run(
            [
                "kubectl",
                "-n",
                namespace,
                "create",
                "secret",
                "generic",
                hf_secret,
                f"--from-literal=HF_TOKEN={hf_token}",
            ]
        )

    # Destroy any existing release set
    if destroy_first:
        _run(["helmfile", "destroy", "-n", namespace], cwd=work_dir)
        # Ensure all old vLLM pods are gone before proceeding
        _wait_for_pods_deleted(
            namespace, f"app.kubernetes.io/instance={ms_release}"
        )

    # Apply infra first
    _run(
        [
            "helmfile",
            "-f",
            helmfile_path,
            "-l",
            f"name={infra_release}",
            "apply",
            "-n",
            namespace,
        ],
        cwd=work_dir,
    )

    # Resolve GAIE override files strictly relative to this script, if provided
    gaie_resolved_overrides: List[str] = []
    if gaie_helmfile_overrides_value:
        if isinstance(gaie_helmfile_overrides_value, (list, tuple, ListConfig)):
            gaie_items = [str(x) for x in gaie_helmfile_overrides_value if str(x).strip()]
        else:
            s = str(gaie_helmfile_overrides_value).strip()
            parsed: List[str] = []
            if s.startswith("[") and s.endswith("]"):
                try:
                    val = ast.literal_eval(s)
                    if isinstance(val, (list, tuple)):
                        parsed = [str(x) for x in val if str(x).strip()]
                except Exception:
                    pass
            if not parsed and "," in s:
                parsed = [part.strip() for part in s.split(",") if part.strip()]
            gaie_items = parsed if parsed else ([s] if s else [])

        if gaie_items:
            script_dir = os.path.dirname(__file__)
            for item in gaie_items:
                candidate = os.path.join(script_dir, item)
                if not os.path.isfile(candidate):
                    print(f"GAIE overrides file not found at: {candidate}")
                    sys.exit(1)
                gaie_resolved_overrides.append(candidate)

    # Optional: synthesize a GAIE plugin values file if config/custom_config provided
    temp_gaie_values_path = None

    # Apply GAIE with optional overrides
    gaie_cmd = [
        "helmfile",
        "-f",
        helmfile_path,
        "-l",
        f"name={gaie_release}",
        "apply",
        "-n",
        namespace,
    ]
    if gaie_resolved_overrides:
        gaie_values_parts = " ".join([f"--values {p}" for p in gaie_resolved_overrides])
        gaie_cmd.extend(["--args", gaie_values_parts])
    try:
        _run(gaie_cmd, cwd=work_dir)
    finally:
        if temp_gaie_values_path:
            try:
                os.unlink(temp_gaie_values_path)
            except OSError:
                pass

    # Resolve override files strictly relative to this script, if provided
    resolved_overrides: List[str] = []
    if helmfile_overrides_value:
        # Accept a Hydra ListConfig / list / tuple, or parse string forms
        if isinstance(helmfile_overrides_value, (list, tuple, ListConfig)):
            override_items = [str(x) for x in helmfile_overrides_value if str(x).strip()]
        else:
            s = str(helmfile_overrides_value).strip()
            parsed: List[str] = []
            if s.startswith("[") and s.endswith("]"):
                try:
                    val = ast.literal_eval(s)
                    if isinstance(val, (list, tuple)):
                        parsed = [str(x) for x in val if str(x).strip()]
                except Exception:
                    pass
            if not parsed and "," in s:
                parsed = [part.strip() for part in s.split(",") if part.strip()]
            override_items = parsed if parsed else ([s] if s else [])

        if override_items:
            script_dir = os.path.dirname(__file__)
            for item in override_items:
                candidate = os.path.join(script_dir, item)
                if not os.path.isfile(candidate):
                    print(f"Overrides file not found at: {candidate}")
                    sys.exit(1)
                resolved_overrides.append(candidate)

    # Apply ms; add overrides only when provided
    ms_cmd = [
        "helmfile",
        "-f",
        helmfile_path,
        "-l",
        f"name={ms_release}",
        "apply",
        "-n",
        namespace,
    ]
    args_parts = []
    if resolved_overrides:
        args_parts.append(" ".join([f"--values {p}" for p in resolved_overrides]))
    # Always set replicas via --set so no values file is required for that scalar
    args_parts.append(f"--set decode.replicas={decode_replicas}")
    # Set tensor parallelism for decode via --set
    # args_parts.append(f"--set decode.parallelism.tensor={decode_tp}")
    # Also append explicit vLLM arg via container args so it shows up in the command line without chart edits.
    # Use Kubernetes env expansion syntax $(TP_SIZE) so the value comes from the container env.
    if decode_tp and decode_tp > 1:
        # Base values.yaml already defines two args; append after them to avoid overwrite.
        args_parts.append("--set-string decode.containers[0].args[2]=--tensor-parallel-size")
        args_parts.append("--set-string decode.containers[0].args[3]=$(TP_SIZE)")
        # Force multiprocessing executor to avoid Ray at TP>1
        args_parts.append("--set-string decode.containers[0].args[4]=--distributed-executor-backend")
        args_parts.append("--set-string decode.containers[0].args[5]=mp")
        # Ensure at least two GPUs are visible when TP>1; override CUDA_VISIBLE_DEVICES from base values.
        # Note: base values set env[0] to CUDA_VISIBLE_DEVICES; override just its value.
        # Build device list "0..N-1" and escape commas so Helm does not split the value
        _cuda_list = "\\,".join(str(i) for i in range(max(decode_tp, 1)))
        args_parts.append(f"--set-string decode.containers[0].env[0].value={_cuda_list}")
    ms_cmd.extend(["--args", " ".join(args_parts)])
    _run(ms_cmd, cwd=work_dir)

    # Optional HTTPRoute manifest (shared for istio/kgateway providers)
    httproute_path = os.path.join(work_dir, "httproute.yaml")
    if os.path.isfile(httproute_path):
        print("Applying HTTPRoute...")
        _run(["kubectl", "-n", namespace, "apply", "-f", httproute_path])

    # Readiness check: ensure all vLLM pods respond locally, then gateway
    # Use the configured run.model when available; fall back to a sensible default
    model = None
    try:
        # If config contains the run group use that model
        model = str(cfg.run.model)
    except Exception:
        model = "Qwen/Qwen3-0.6B"
    wait_until_ready(namespace=namespace, model=model)


if __name__ == "__main__":
    main()


