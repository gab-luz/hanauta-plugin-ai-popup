import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from hanauta_aipopup.backends import lfm3_build_env, llama_build_plan  # noqa: E402
from hanauta_aipopup.catalog import find_entry  # noqa: E402


def test_find_entry_returns_lfm3_pin():
    entry = find_entry("lfm3_omni_2b_abliter8")
    assert entry is not None
    assert entry["llama_git_ref"] == "d05706b4b"
    assert "Q6_K" in str(entry.get("prefer_quant", ""))
    assert find_entry("does-not-exist") is None


def test_build_env_matrix_patch_and_gpu():
    plan = llama_build_plan({"llama_runtime_flavor": "lfm3"})
    env = lfm3_build_env(
        plan,
        {
            "llama_compute_backend": "cpu cuda",
            "device": "gpu",
            "llama_patch_url": "https://example.invalid/lfm3.patch",
        },
    )
    assert env["BACKENDS"] == "cpu cuda"
    assert env["PATCH_URL"] == "https://example.invalid/lfm3.patch"
    assert env["CMAKE_EXTRA"] == "-DGGML_CUDA=ON"
    assert env["LLAMA_REF"] == "d05706b4b"
    assert env["PREFIX"] == str(plan["install_root"])
    # Verification is opt-in: no model paths leaked into a plain build.
    assert "SMOKE_MODEL" not in env


def test_build_env_verify_is_opt_in():
    plan = llama_build_plan({"llama_runtime_flavor": "lfm3"})
    files = {"gguf_path": "/models/m.gguf", "mmproj_path": "/models/mmproj.gguf"}
    assert "SMOKE_MODEL" not in lfm3_build_env(plan, dict(files))

    env = lfm3_build_env(plan, {**files, "llama_verify_after_build": True})
    assert env["SMOKE_MODEL"] == "/models/m.gguf"
    assert env["SMOKE_MMPROJ"] == "/models/mmproj.gguf"
    assert env["BACKENDS"] == "cpu"


def test_build_env_defaults_pin_the_evaluated_commit():
    # The lfm3 flavor must carry the evaluated commit; other flavors stay upstream.
    env = lfm3_build_env(llama_build_plan({"llama_runtime_flavor": "lfm3"}), {})
    assert env["LLAMA_REF"] == "d05706b4b"
    assert "PATCH_URL" not in env
    assert llama_build_plan({})["flavor"] == "upstream"
