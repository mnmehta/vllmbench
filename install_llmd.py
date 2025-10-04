import os
import ast
import subprocess
import sys
from typing import List

import hydra
from omegaconf import DictConfig, ListConfig


def _run(cmd: List[str], cwd: str | None = None) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=cwd)


def _ensure_repo(repo_url: str, clone_dir: str) -> None:
    if not os.path.isdir(clone_dir):
        _run(["git", "clone", repo_url, clone_dir])


@hydra.main(config_path="conf", config_name="config", version_base=None)
def main(cfg: DictConfig) -> None:
    repo_url = cfg.install.repo_url
    llmd_dir = cfg.install.llmd_dir
    well_lit_path = cfg.install.well_lit_path
    helmfile_overrides_value = cfg.install.helmfile_overrides
    namespace = cfg.install.namespace
    helmfile_path = cfg.install.helmfile_path
    destroy_first = bool(cfg.install.destroy_first)

    # Clone if missing
    _ensure_repo(repo_url, llmd_dir)

    work_dir = os.path.join(llmd_dir, well_lit_path)
    if not os.path.isdir(work_dir):
        print(f"Work directory not found: {work_dir}")
        sys.exit(1)

    # Destroy any existing release set
    if destroy_first:
        _run(["helmfile", "destroy", "-n", namespace], cwd=work_dir)

    # Apply infra and gaie
    _run(["helmfile", "-f", helmfile_path, "-l", "name=infra-inference-scheduling", "apply", "-n", namespace], cwd=work_dir)
    _run(["helmfile", "-f", helmfile_path, "-l", "name=gaie-inference-scheduling", "apply", "-n", namespace], cwd=work_dir)

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
        "name=ms-inference-scheduling",
        "apply",
        "-n",
        namespace,
    ]
    if resolved_overrides:
        values_parts = " ".join([f"--values {p}" for p in resolved_overrides])
        ms_cmd.extend(["--args", values_parts])
    _run(ms_cmd, cwd=work_dir)


if __name__ == "__main__":
    main()


