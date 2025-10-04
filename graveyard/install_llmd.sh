#! /bin/bash


base=$(dirname $(realpath $0))
llmd_dir="/tmp/llmd"
well_lit_path="guides/inference-scheduling/"
overrides="$base/override_ms_70b.yaml"
namespace="llm-d-inference-scheduler"

if [ ! -d $llmd_dir ]; then
    git clone https://github.com/llm-d/llm-d $llmd_dir
fi

cd ${llmd_dir}/${well_lit_path}
helmfile destroy -n $namespace
# Apply infra and gaie normally:
helmfile -f helmfile.yaml.gotmpl -l name=infra-inference-scheduling apply -n $namespace
helmfile -f helmfile.yaml.gotmpl -l name=gaie-inference-scheduling apply -n $namespace

# Apply ms with your override values:
helmfile -f helmfile.yaml.gotmpl -l name=ms-inference-scheduling apply --args "--values ${overrides}" -n $namespace