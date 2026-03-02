"""
download_all_models.py

Downloads ALL models required by WalkSense AI:
  1. YOLO   — Object detection (yolo11m, yolov8n)
  2. VLM    — Vision-Language Model (active_model from config, e.g. Qwen2-VL / Qwen3-VL)
  3. LLM    — Language Model (active_model from config, e.g. Phi-2 / Phi-4-mini)
  4. STT    — Speech-to-Text (active_model from config, e.g. whisper-small / medium / large)
  5. TTS    — Text-to-Speech (Coqui TTS vits model)
  6. DEPTH  — Monocular Depth Estimation (Depth Anything V2 / MiDaS)

Usage:
    python download_all_models.py                    # Download everything
    python download_all_models.py --only yolo         # Download only YOLO
    python download_all_models.py --only vlm llm depth # Selective
    python download_all_models.py --skip tts           # Skip TTS
    python download_all_models.py --list               # Show registered models

Extensibility:
    To add a new model type, define a download_xxx(config) function and
    register it in the DOWNLOADERS dict at the bottom of this file.
"""

import os
import sys
import json
import shutil
import argparse
import importlib
from pathlib import Path

# ── Resolve project paths ──────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).resolve().parent                 # Scripts/Download_Model/
SCRIPTS_DIR = SCRIPT_DIR.parent                               # Scripts/
INFERENCE_DIR = SCRIPTS_DIR.parent                            # Inference/
MODELS_DIR  = INFERENCE_DIR / "Models"                        # Inference/Models/
CONFIG_PATH = INFERENCE_DIR / "config.json"

# Create base model directories
YOLO_DIR    = MODELS_DIR / "yolo"
VLM_DIR     = MODELS_DIR / "vlm"
LLM_DIR     = MODELS_DIR / "llm"
STT_DIR     = MODELS_DIR / "stt"
TTS_DIR     = MODELS_DIR / "tts"
WHISPER_DIR = STT_DIR / "whisper"                             # Subfolder for faster-whisper / openai-whisper cache
DEPTH_DIR   = MODELS_DIR / "depth"                            # Depth estimation models


# ── Helpers ─────────────────────────────────────────────────────────────────────
def _header(title: str):
    width = 60
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}")


def _ok(msg: str):
    print(f"  [OK]   {msg}")


def _skip(msg: str):
    print(f"  [SKIP] {msg}")


def _fail(msg: str):
    print(f"  [FAIL] {msg}")


def _info(msg: str):
    print(f"  [INFO] {msg}")


def load_config() -> dict:
    """Load config.json from the Inference directory."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    _info(f"config.json not found at {CONFIG_PATH}, using defaults.")
    return {}


def ensure_dir(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)


# Providers that require downloading model files locally.
# If the active_provider is NOT in this set, the download is skipped.
LOCAL_PROVIDERS = {"local", "huggingface_api", "coqui"}


def _needs_download(config: dict, section: str, force: bool = False) -> bool:
    """Check if the active provider for a config section requires a local model download."""
    if force:
        return True
    provider = config.get(section, {}).get("active_provider", "")
    if provider in LOCAL_PROVIDERS:
        return True
    _skip(f"{section}.active_provider = '{provider}' — no local download needed")
    _info(f"  (Use --force to download anyway, or set active_provider to 'local')")
    return False


# ── 1. YOLO ────────────────────────────────────────────────────────────────────
def download_yolo(config: dict, force: bool = False):
    _header("YOLO — Object Detection Models")
    ensure_dir(YOLO_DIR)

    try:
        from ultralytics import YOLO
    except ImportError:
        _fail("ultralytics not installed.  Run:  pip install ultralytics")
        return False

    # Gather model names from config
    detector_cfg = config.get("detector", {})
    model_map = detector_cfg.get("models", {
        "yolov8n": "Models/yolo/yolov8n.pt",
        "yolo11m": "Models/yolo/yolo11m.pt",
    })

    success = True
    for name, rel_path in model_map.items():
        filename = Path(rel_path).name                       # e.g. yolo11m.pt
        target = YOLO_DIR / filename

        if target.exists():
            _skip(f"{filename} already exists at {target}")
            continue

        _info(f"Downloading {filename} ...")
        try:
            # Ultralytics downloads to cwd by default
            original_cwd = os.getcwd()
            os.chdir(str(YOLO_DIR))
            _ = YOLO(filename)                               # triggers download
            os.chdir(original_cwd)

            # If file ended up in cwd (YOLO_DIR already) we're fine
            if target.exists():
                _ok(f"{filename} → {target}")
            else:
                # Check if it landed in the original cwd
                alt = Path(original_cwd) / filename
                if alt.exists():
                    shutil.move(str(alt), str(target))
                    _ok(f"{filename} → {target}")
                else:
                    _fail(f"{filename} not found after download attempt")
                    success = False
        except Exception as e:
            _fail(f"{filename}: {e}")
            success = False

    return success


# ── 2. VLM ──────────────────────────────────────────────────────────────────────
def download_vlm(config: dict, force: bool = False):
    _header("VLM — Vision-Language Model")

    if not _needs_download(config, "vlm", force):
        return True

    ensure_dir(VLM_DIR)

    try:
        from transformers import AutoProcessor, AutoModelForImageTextToText
    except ImportError:
        _fail("transformers not installed.  Run:  pip install transformers accelerate")
        return False

    # Read from config — local provider now has active_model + models dict
    vlm_cfg      = config.get("vlm", {}).get("providers", {}).get("local", {})
    active_model = vlm_cfg.get("active_model", "qwen2-vl-2b")
    models_cfg   = vlm_cfg.get("models", {})
    model_cfg    = models_cfg.get(active_model, {})
    model_id     = model_cfg.get("model_id", "Qwen/Qwen2-VL-2B-Instruct")
    local_name   = model_cfg.get("local_model_path", f"Models/vlm/{active_model}")
    save_dir     = VLM_DIR / Path(local_name).name

    _info(f"Active local model: {active_model} → {model_id}")

    if save_dir.exists() and any(save_dir.iterdir()):
        _skip(f"{model_id} already downloaded at {save_dir}")
        return True

    ensure_dir(save_dir)
    _info(f"Downloading processor for {model_id} ...")
    try:
        processor = AutoProcessor.from_pretrained(model_id)
        processor.save_pretrained(str(save_dir))
        _ok(f"Processor saved to {save_dir}")
    except Exception as e:
        _fail(f"Processor download failed: {e}")
        return False

    _info(f"Downloading model weights for {model_id} (this may take a while) ...")
    try:
        model = AutoModelForImageTextToText.from_pretrained(
            model_id,
            torch_dtype="auto",
            device_map="cpu",                                # download only, no GPU needed
            trust_remote_code=True,
        )
        model.save_pretrained(str(save_dir))
        _ok(f"Model saved to {save_dir}")
    except Exception as e:
        _fail(f"Model download failed: {e}")
        return False

    return True


# ── 3. LLM ──────────────────────────────────────────────────────────────────────
def download_llm(config: dict, force: bool = False):
    _header("LLM — Language Model")

    if not _needs_download(config, "llm", force):
        return True

    ensure_dir(LLM_DIR)

    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError:
        _fail("transformers not installed.  Run:  pip install transformers accelerate")
        return False

    # Read from config — local provider now has active_model + models dict
    llm_cfg      = config.get("llm", {}).get("providers", {}).get("local", {})
    active_model = llm_cfg.get("active_model", "phi-2")
    models_cfg   = llm_cfg.get("models", {})
    model_cfg    = models_cfg.get(active_model, {})
    model_id     = model_cfg.get("model_id", "microsoft/phi-2")
    local_name   = model_cfg.get("local_model_path", f"Models/llm/{active_model}")
    save_dir     = LLM_DIR / Path(local_name).name

    _info(f"Active local model: {active_model} → {model_id}")

    if save_dir.exists() and any(save_dir.iterdir()):
        _skip(f"{model_id} already downloaded at {save_dir}")
        return True

    ensure_dir(save_dir)
    _info(f"Downloading tokenizer for {model_id} ...")
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        tokenizer.save_pretrained(str(save_dir))
        _ok(f"Tokenizer saved to {save_dir}")
    except Exception as e:
        _fail(f"Tokenizer download failed: {e}")
        return False

    _info(f"Downloading model weights for {model_id} (this may take a while) ...")
    try:
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype="auto",
            device_map="cpu",
        )
        model.save_pretrained(str(save_dir))
        _ok(f"Model saved to {save_dir}")
    except Exception as e:
        _fail(f"Model download failed: {e}")
        return False

    return True


# ── 4. STT ──────────────────────────────────────────────────────────────────────
def download_stt(config: dict, force: bool = False):
    _header("STT — Speech-to-Text (Whisper)")

    if not _needs_download(config, "stt", force):
        return True

    ensure_dir(STT_DIR)
    ensure_dir(WHISPER_DIR)

    stt_cfg = config.get("stt", {}).get("providers", {}).get("local", {})

    # Resolve active model from nested models dict
    active_model = stt_cfg.get("active_model", "whisper-small")
    models_cfg   = stt_cfg.get("models", {})
    model_cfg    = models_cfg.get(active_model, {})
    model_size   = model_cfg.get("model_size", "small")

    _info(f"Active local model: {active_model} (size: {model_size})")

    # Strategy: try faster-whisper first, then fall back to openai-whisper
    downloaded = False

    # ── faster-whisper ──
    try:
        from faster_whisper import WhisperModel
        _info(f"Downloading faster-whisper model '{model_size}' (CTranslate2 format) ...")
        _info(f"Cache directory: {WHISPER_DIR}")

        # WhisperModel downloads to download_root on first load
        model = WhisperModel(model_size, device="cpu", compute_type="int8", download_root=str(WHISPER_DIR))
        _ok(f"faster-whisper '{model_size}' ready at {WHISPER_DIR}")
        downloaded = True
        del model
    except ImportError:
        _info("faster-whisper not installed, trying openai-whisper ...")
    except Exception as e:
        _fail(f"faster-whisper download failed: {e}")
        _info("Trying openai-whisper as fallback ...")

    # ── openai-whisper ──
    if not downloaded:
        try:
            import whisper
            _info(f"Downloading openai-whisper model '{model_size}' ...")
            model = whisper.load_model(model_size, download_root=str(WHISPER_DIR))
            _ok(f"openai-whisper '{model_size}' ready at {WHISPER_DIR}")
            downloaded = True
            del model
        except ImportError:
            _fail("Neither faster-whisper nor openai-whisper is installed.")
            _fail("Run:  pip install faster-whisper  OR  pip install openai-whisper")
            return False
        except Exception as e:
            _fail(f"openai-whisper download failed: {e}")
            return False

    # ── Also download HuggingFace whisper model (used by some STT providers) ──
    hf_model_id = config.get("stt", {}).get("providers", {}).get("huggingface_api", {}).get("model_id", "")
    if hf_model_id:
        hf_save_dir = STT_DIR / f"whisper-{model_size}"
        if hf_save_dir.exists() and any(hf_save_dir.iterdir()):
            _skip(f"HuggingFace {hf_model_id} already at {hf_save_dir}")
        else:
            try:
                from transformers import WhisperProcessor, WhisperForConditionalGeneration
                ensure_dir(hf_save_dir)
                _info(f"Downloading HuggingFace Whisper processor ({hf_model_id}) ...")
                processor = WhisperProcessor.from_pretrained(hf_model_id)
                processor.save_pretrained(str(hf_save_dir))
                _info(f"Downloading HuggingFace Whisper model ({hf_model_id}) ...")
                model = WhisperForConditionalGeneration.from_pretrained(hf_model_id)
                model.save_pretrained(str(hf_save_dir))
                _ok(f"HuggingFace Whisper saved to {hf_save_dir}")
                del model, processor
            except ImportError:
                _info("transformers not available — skipping HuggingFace Whisper download.")
            except Exception as e:
                _fail(f"HuggingFace Whisper download failed: {e}")

    return downloaded


# ── 5. TTS ──────────────────────────────────────────────────────────────────────
def download_tts(config: dict, force: bool = False):
    _header("TTS — Text-to-Speech")

    if not _needs_download(config, "tts", force):
        return True

    ensure_dir(TTS_DIR)

    tts_cfg = config.get("tts", {}).get("providers", {})

    # ── Coqui TTS model ──
    coqui_model = tts_cfg.get("coqui", {}).get("model", "tts_models/en/ljspeech/vits")
    downloaded = False

    try:
        from TTS.api import TTS as CoquiTTS
        _info(f"Downloading Coqui TTS model: {coqui_model} ...")
        tts = CoquiTTS(model_name=coqui_model, progress_bar=True)
        _ok(f"Coqui TTS model '{coqui_model}' downloaded and cached.")
        downloaded = True
        del tts
    except ImportError:
        _info("Coqui TTS (TTS package) not installed.")
        _info("Install with:  pip install TTS")
        _info("Skipping Coqui TTS download.")
    except Exception as e:
        _fail(f"Coqui TTS download failed: {e}")

    # ── HuggingFace TTS (fastspeech2) ──
    hf_model_id = tts_cfg.get("huggingface_api", {}).get("model_id", "")
    if hf_model_id:
        hf_save_dir = TTS_DIR / hf_model_id.replace("/", "--")
        if hf_save_dir.exists() and any(hf_save_dir.iterdir()):
            _skip(f"HuggingFace TTS {hf_model_id} already at {hf_save_dir}")
        else:
            try:
                from transformers import AutoModel, AutoProcessor
                ensure_dir(hf_save_dir)
                _info(f"Downloading HuggingFace TTS model: {hf_model_id} ...")
                processor = AutoProcessor.from_pretrained(hf_model_id)
                processor.save_pretrained(str(hf_save_dir))
                model = AutoModel.from_pretrained(hf_model_id)
                model.save_pretrained(str(hf_save_dir))
                _ok(f"HuggingFace TTS model saved to {hf_save_dir}")
                downloaded = True
                del model, processor
            except ImportError:
                _info("transformers not available — skipping HuggingFace TTS download.")
            except Exception as e:
                _info(f"HuggingFace TTS model ({hf_model_id}) download skipped: {e}")

    if not downloaded:
        _info("No TTS models were downloaded. The default pyttsx3 provider needs no model files.")
        _info("pyttsx3 uses your OS's built-in speech engine (SAPI5 on Windows).")
        return True                                           # Not a failure

    return True


# ── 6. DEPTH ────────────────────────────────────────────────────────────────────
def download_depth(config: dict, force: bool = False):
    _header("DEPTH — Monocular Depth Estimation")
    ensure_dir(DEPTH_DIR)

    try:
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation
    except ImportError:
        _fail("transformers not installed.  Run:  pip install transformers")
        return False

    depth_cfg = config.get("depth", {})
    if not depth_cfg.get("enabled", True):
        _skip("Depth estimation is disabled in config.json")
        return True

    # Download the active model (and optionally all configured models)
    active_key = depth_cfg.get("active_model", "depth_anything_v2_small")
    models_cfg = depth_cfg.get("models", {
        "depth_anything_v2_small": {
            "model_id": "depth-anything/Depth-Anything-V2-Small",
            "local_model_path": "Models/depth/depth-anything-v2-small",
        }
    })

    # Only download the active model by default
    targets = {active_key: models_cfg[active_key]} if active_key in models_cfg else models_cfg

    success = True
    for key, mcfg in targets.items():
        model_id   = mcfg.get("model_id", "")
        local_path = mcfg.get("local_model_path", f"Models/depth/{key}")
        save_dir   = DEPTH_DIR / Path(local_path).name

        if save_dir.exists() and any(save_dir.iterdir()):
            _skip(f"{model_id} already downloaded at {save_dir}")
            continue

        ensure_dir(save_dir)
        _info(f"Downloading depth processor: {model_id} ...")
        try:
            processor = AutoImageProcessor.from_pretrained(model_id)
            processor.save_pretrained(str(save_dir))
            _ok(f"Processor saved to {save_dir}")
        except Exception as e:
            _fail(f"Processor download failed for {model_id}: {e}")
            success = False
            continue

        _info(f"Downloading depth model weights: {model_id} (this may take a while) ...")
        try:
            model = AutoModelForDepthEstimation.from_pretrained(model_id)
            model.save_pretrained(str(save_dir))
            _ok(f"Depth model saved to {save_dir}")
            del model
        except Exception as e:
            _fail(f"Depth model download failed for {model_id}: {e}")
            success = False

    return success


# ══════════════════════════════════════════════════════════════════════════════════
#  PLUGGABLE MODEL REGISTRY
# ══════════════════════════════════════════════════════════════════════════════════
#
#  To add a NEW model type:
#    1. Write a  download_xxx(config: dict) -> bool  function above.
#    2. Add an entry here:  "xxx": (download_xxx, "Short description")
#    3. (Optional) Add config section to config.json.
#
#  The CLI flags (--only / --skip) auto-discover keys from this dict.
# ──────────────────────────────────────────────────────────────────────────────────

DOWNLOADERS = {
    "yolo":  (download_yolo,  "Object detection (YOLO v8/v11)"),
    "vlm":   (download_vlm,   "Vision-Language Model (config: vlm.providers.local.active_model)"),
    "llm":   (download_llm,   "Language Model (config: llm.providers.local.active_model)"),
    "stt":   (download_stt,   "Speech-to-Text (Whisper)"),
    "tts":   (download_tts,   "Text-to-Speech (Coqui / pyttsx3)"),
    "depth": (download_depth,  "Monocular Depth Estimation (Depth Anything V2 / MiDaS)"),
}


def _print_registry():
    """Pretty-print all registered model downloaders."""
    _header("Registered Model Downloaders")
    for key, (_, desc) in DOWNLOADERS.items():
        print(f"  {key:<8}  {desc}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Download all WalkSense AI models (YOLO, VLM, LLM, STT, TTS, Depth)"
    )
    parser.add_argument(
        "--only", nargs="+", choices=DOWNLOADERS.keys(), default=None,
        help="Download only the specified model types (e.g. --only vlm stt depth)"
    )
    parser.add_argument(
        "--skip", nargs="+", choices=DOWNLOADERS.keys(), default=None,
        help="Skip the specified model types (e.g. --skip yolo tts)"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Download models even if active_provider doesn't require local files"
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List all registered model types and exit"
    )
    args = parser.parse_args()

    if args.list:
        _print_registry()
        return 0

    # Determine which models to download
    targets = list(DOWNLOADERS.keys())
    if args.only:
        targets = args.only
    if args.skip:
        targets = [t for t in targets if t not in args.skip]

    print("=" * 60)
    print("  WalkSense AI — Model Downloader")
    print(f"  Models to download: {', '.join(targets)}")
    print(f"  Model root: {MODELS_DIR}")
    print("=" * 60)

    config = load_config()
    results = {}

    for name in targets:
        try:
            fn, _ = DOWNLOADERS[name]
            results[name] = fn(config, force=args.force)
        except Exception as e:
            _fail(f"Unexpected error downloading {name}: {e}")
            results[name] = False

    # ── Summary ──
    _header("Download Summary")
    all_ok = True
    for name in targets:
        icon = "[OK]  " if results.get(name) else "[FAIL]"
        print(f"  {icon} {name.upper()}")
        if not results.get(name):
            all_ok = False

    if all_ok:
        print(f"\n  All models downloaded successfully!")
    else:
        print(f"\n  Some downloads failed. Check the output above for details.")

    print(f"  Model directory: {MODELS_DIR}\n")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
