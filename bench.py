import subprocess
import re
import mlflow
import sys
import os

# Configuration
CONCURRENCIES = [1,2,4,8,16,32,64,128,256]
INPUT_LEN = 1000
OUTPUT_LEN = 1000
QUERIES_PER_USER = 20
MODEL = "Qwen/Qwen3-0.6B"
#MODEL = "RedHatAI/Llama-3.3-70B-Instruct-FP8-dynamic"
#MODEL = "deepseek-ai/DeepSeek-R1-0528"
#MODEL = "Qwen/Qwen3-30B-A3B"
FRAMEWORK = "vllm"

target_type = os.environ.get("TARGET_TYPE", "").lower()
if target_type == "gateway":
  TARGET = "http://infra-inference-scheduling-inference-gateway-istio"
elif target_type == "direct":
  TARGET = "http://10.130.1.253:8000"
else:
    print(f"Unknown TARGET_TYPE: {target_type!r}")
    sys.exit(1)

# MLflow experiment
mlflow.set_experiment(f"llm-d-version_oct1_{INPUT_LEN}_osl{OUTPUT_LEN}")

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

# Determine this script's filename
script_file = os.path.abspath(__file__)

seed=12345678
for concurrency in CONCURRENCIES:
    num_prompts = QUERIES_PER_USER * concurrency

    print(f"\n===== {FRAMEWORK} - RUNNING {MODEL} FOR {num_prompts} PROMPTS WITH {concurrency} CONCURRENCY {target_type} TARGET =====\n")

    #name=f"vllmdirect_conc{concurrency}"
    name=f"{target_type}_conc{concurrency}"
    with mlflow.start_run(run_name=name) as run:
        # Log parameters
        mlflow.log_param("framework", FRAMEWORK)
        mlflow.log_param("model", MODEL)
        mlflow.log_param("input_len", INPUT_LEN)
        mlflow.log_param("output_len", OUTPUT_LEN)
        mlflow.log_param("concurrency", concurrency)
        mlflow.log_metric("concurrency", concurrency) #Do this so I can sort by concurrency in the UI, params are always sorted lexically whereas metrics can be numeric
        mlflow.log_param("num_prompts", num_prompts)
        mlflow.log_param("queries_per_user", QUERIES_PER_USER)
        mlflow.log_param("target", target_type)

        # Log this script as an artifact
        mlflow.log_artifact(script_file, artifact_path="source_code")

        # Run the benchmark via subprocess
        cmd = [
            #"vllm", "bench", "serve",
            "python","vllm-benchmark/benchmarks/benchmark_serving.py",
            "--model", MODEL,
            "--base-url", TARGET,
            "--dataset-name", "random",
            "--random-input-len", str(INPUT_LEN),
            "--random-output-len", str(OUTPUT_LEN),
            "--max-concurrency", str(concurrency),
            "--num-prompts", str(num_prompts),
            "--seed", str(seed),
            "--ignore-eos"
        ]
        seed = seed + 1

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
        metrics = {}
        for key, pattern in METRIC_PATTERNS.items():
            match = re.search(pattern, output)
            if match:
                metrics[key] = float(match.group(1))

        # Log metrics to MLflow
        for metric_name, value in metrics.items():
            mlflow.log_metric(metric_name, value)

