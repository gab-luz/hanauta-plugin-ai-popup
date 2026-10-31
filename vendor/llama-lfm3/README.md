# Vendored LFM3 llama.cpp runtime

Drop-in runtime so LFM3-Omni works without the user compiling anything.

- `llama-server` is built from llama.cpp at the commit the model card pins
  (`d05706b4d`/`d05706b4b`) **plus** the server patch from
  [`abliter8-ai/lfm3-abliter8-serving`](https://github.com/abliter8-ai/lfm3-abliter8-serving)
  (`patches/llama.cpp-lfm3-server.patch`), which the card documents as required.
- The `lib*.so*` files are the libraries that binary links against. They must
  stay next to it: the launcher prepends this directory to `LD_LIBRARY_PATH`.

## How it is used

`hanauta_aipopup.backends._prebuilt_llama_server()` checks, in order:

1. `llama_server_binary` / `binary_path` from the backend settings,
2. the installed runtime under `~/.cache/hanauta-ai-popup/runtimes/lfm3-llama-cpp/`,
3. this directory.

If a binary is found here, the settings window fills the binary path with it and
no build runs.

## Rebuilding / replacing

```bash
./scripts/build_llama_lfm3.sh --force            # pinned commit + patch
cp -aL ~/.cache/hanauta-ai-popup/runtimes/lfm3-llama-cpp/cpu/llama-server \
      ~/.cache/hanauta-ai-popup/runtimes/lfm3-llama-cpp/cpu/lib*.so* vendor/llama-lfm3/
```

This drop-in is **CPU-only** (backend `cpu`). For CUDA/ROCm/Vulkan builds, use
`BACKENDS="cuda" ./scripts/build_llama_lfm3.sh`; the settings window's
"compile automatically" path then installs it and fills in the binary field.
Flash Attention and MTP are auto-enabled only when the build reports a GPU
backend and advertises the flag.

A GPU runtime can also be dropped in at `vendor/llama-lfm3-cuda/`, which is
checked before this directory. It is not committed: `libggml-cuda.so` alone is
~150 MB, so GPU users build locally in one click instead.

Licence: llama.cpp is MIT. The patch comes from the Abliter8 serving repo; the
model weights are covered by the LFM Open License v1.0.
