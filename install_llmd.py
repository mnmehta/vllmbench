import os
import subprocess
import sys
from typing import List

import hydra
from omegaconf import DictConfig


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
    helmfile_overrides = str(helmfile_overrides_value) if helmfile_overrides_value is not None else ""
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

    # Resolve overrides file strictly relative to this script, if provided
    resolved_override: str | None = None
    if helmfile_overrides.strip():
        script_dir = os.path.dirname(__file__)
        candidate = os.path.join(script_dir, helmfile_overrides)
        if not os.path.isfile(candidate):
            print(f"Overrides file not found at: {candidate}")
            sys.exit(1)
        resolved_override = candidate

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
    if resolved_override is not None:
        ms_cmd.extend(["--args", f"--values {resolved_override}"])
    _run(ms_cmd, cwd=work_dir)


if __name__ == "__main__":
    main()


