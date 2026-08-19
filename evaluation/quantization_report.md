# Quantization Report — Biscuits Focus

Base: experiment_003 (LoRA r=32) merged, converted to GGUF, quantized via Ollama's built-in quantizer.

Note: Q5_K_M is not supported by Ollama's quantizer on this version (supported: F32, F16, Q4_K_S, Q4_K_M, Q8_0) — comparing Q4_K_M / Q8_0 / F16 instead.

| Variant | Size | JSON valid % | Avg tok/s | Avg latency | First load |
|---|---|---|---|---|---|
| biscuits-focus-q4 | 807.0 MB | 92.9 | 229.9 | 0.92s | 4.36s |
| biscuits-focus-q8 | 1331.0 MB | 78.6 | 154.7 | 1.23s | 4.3s |
| biscuits-focus-f16 | 2560.0 MB | 85.7 | 45.6 | 2.78s | 6.78s |