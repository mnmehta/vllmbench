# Dynamic Override Examples

The `install_llmd.py` script generates temporary Helm values override files instead of hardcoding argument indices. This document shows what these override files look like.

## Why Dynamic Overrides?

**Problem with hardcoded indices:**
```python
# BAD: Fragile - breaks if base values.yaml changes
args_parts.append("--set-string decode.containers[0].args[7]=--no-enable-prefix-caching")
```

**Solution with dynamic override:**
```python
# GOOD: More robust - uses YAML overrides instead of index math
override_data = {
    "decode": {
        "containers": [{
            "name": "vllm",
            "image": "ghcr.io/llm-d/llm-d-cuda:v0.3.1",  # Required by chart
            "modelCommand": "vllmServe",                  # Required by chart
            "args": ["--no-enable-prefix-caching"]
        }]
    }
}
```

**Why we need `image` and `modelCommand`:**
Helm's strategic merge uses the container `name` as a merge key. When merging containers by name, the chart template validation requires `image` to be present. We use the base values.yaml defaults for these fields. User override files (loaded after our dynamic override) can override them if needed.

## Example Override Files

### Scenario 1: Prefix Cache Disabled Only (TP=1)

**Command:**
```bash
python install_llmd.py --config-name=gptoss120b install.disable_prefix_cache=true
```

**Generated override file:**
```yaml
decode:
  containers:
  - name: vllm
    image: ghcr.io/llm-d/llm-d-cuda:v0.3.1
    modelCommand: vllmServe
    args:
    - --no-enable-prefix-caching
```

**Resulting pod args (after Helm merge):**
```json
[
  "/model-cache/models/openai-gpt-oss-120b",           // Chart-generated
  "--port",                                             // Chart-generated
  "8200",                                               // Chart-generated
  "--served-model-name",                                // Chart-generated
  "openai/gpt-oss-120b",                               // Chart-generated
  "--kv-transfer-config",                               // From base values.yaml
  "{\"kv_connector\":\"NixlConnector\", \"kv_role\":\"kv_both\"}",  // From base values.yaml
  "--disable-uvicorn-access-log",                       // From base values.yaml
  "--no-enable-prefix-caching"                          // From dynamic override
]
```

### Scenario 2: Tensor Parallelism Only (TP=2)

**Command:**
```bash
python install_llmd.py --config-name=gptoss120b install.decode_tp=2
```

**Generated override file:**
```yaml
decode:
  containers:
  - name: vllm
    image: ghcr.io/llm-d/llm-d-cuda:v0.3.1
    modelCommand: vllmServe
    args:
    - --tensor-parallel-size
    - $(TP_SIZE)
    - --distributed-executor-backend
    - mp
    env:
    - name: CUDA_VISIBLE_DEVICES
      value: 0,1
```

**Resulting pod args:**
```json
[
  "/model-cache/models/openai-gpt-oss-120b",
  "--port",
  "8200",
  "--served-model-name",
  "openai/gpt-oss-120b",
  "--kv-transfer-config",
  "{\"kv_connector\":\"NixlConnector\", \"kv_role\":\"kv_both\"}",
  "--disable-uvicorn-access-log",
  "--tensor-parallel-size",                             // From dynamic override
  "2",                                                   // $(TP_SIZE) expanded to 2
  "--distributed-executor-backend",                     // From dynamic override
  "mp"                                                   // From dynamic override
]
```

### Scenario 3: Both TP=2 AND Prefix Cache Disabled

**Command:**
```bash
python install_llmd.py --config-name=gptoss120b install.decode_tp=2 install.disable_prefix_cache=true
```

**Generated override file:**
```yaml
decode:
  containers:
  - name: vllm
    image: ghcr.io/llm-d/llm-d-cuda:v0.3.1
    modelCommand: vllmServe
    args:
    - --tensor-parallel-size
    - $(TP_SIZE)
    - --distributed-executor-backend
    - mp
    - --no-enable-prefix-caching
    env:
    - name: CUDA_VISIBLE_DEVICES
      value: 0,1
```

**Resulting pod args:**
```json
[
  "/model-cache/models/openai-gpt-oss-120b",
  "--port",
  "8200",
  "--served-model-name",
  "openai/gpt-oss-120b",
  "--kv-transfer-config",
  "{\"kv_connector\":\"NixlConnector\", \"kv_role\":\"kv_both\"}",
  "--disable-uvicorn-access-log",
  "--tensor-parallel-size",
  "2",
  "--distributed-executor-backend",
  "mp",
  "--no-enable-prefix-caching"                          // Appended at the end
]
```

### Scenario 4: TP=4 (More GPUs)

**Command:**
```bash
python install_llmd.py --config-name=gptoss120b install.decode_tp=4
```

**Generated override file:**
```yaml
decode:
  containers:
  - name: vllm
    image: ghcr.io/llm-d/llm-d-cuda:v0.3.1
    modelCommand: vllmServe
    args:
    - --tensor-parallel-size
    - $(TP_SIZE)
    - --distributed-executor-backend
    - mp
    env:
    - name: CUDA_VISIBLE_DEVICES
      value: 0,1,2,3
```

**Note:** The `CUDA_VISIBLE_DEVICES` value scales with the TP size.

## Viewing the Generated Override

When you run `install_llmd.py`, it prints the generated override file to stdout:

```
Generated dynamic override: /tmp/llmd_override_abc123.yaml
decode:
  containers:
  - name: vllm
    image: ghcr.io/llm-d/llm-d-cuda:v0.3.1
    modelCommand: vllmServe
    args:
    - --no-enable-prefix-caching
```

The file is automatically deleted after the Helm deployment completes.

## Benefits of This Approach

1. **No hardcoded indices**: Works regardless of how many base args exist
2. **Future-proof**: If base `values.yaml` changes, this still works
3. **Clear and readable**: The override file is self-documenting
4. **Proper merging**: Helm's strategic merge handles array concatenation correctly
5. **Easy to debug**: You can see exactly what's being overridden in the logs

## How Helm Merges Arrays

Helm uses **strategic merge patch** for arrays. When you have:

**Base values.yaml:**
```yaml
containers:
- name: vllm
  args:
  - arg1
  - arg2
```

**Override file:**
```yaml
containers:
- name: vllm
  args:
  - arg3
  - arg4
```

**Result after merge:**
```yaml
containers:
- name: vllm
  args:
  - arg1
  - arg2
  - arg3
  - arg4
```

The arrays are **concatenated**, not replaced, when the container name matches.

## Troubleshooting

### If the override doesn't seem to work

1. Check that the container name in the override matches exactly: `name: vllm`
2. Verify the temp file was created (check the logs for "Generated dynamic override")
3. Check if the temp file was cleaned up (should see "Cleaned up temporary override")
4. Inspect the final pod to see actual args:
   ```bash
   oc get pod <pod-name> -n llm-d-bench -o jsonpath='{.spec.containers[?(@.name=="vllm")].args}'
   ```

### If you want to keep the override file for debugging

Modify the cleanup code in `install_llmd.py`:
```python
# Comment out the cleanup section
# if temp_override_path and os.path.isfile(temp_override_path):
#     os.unlink(temp_override_path)
```

Then you can inspect `/tmp/llmd_override_*.yaml` after deployment.
