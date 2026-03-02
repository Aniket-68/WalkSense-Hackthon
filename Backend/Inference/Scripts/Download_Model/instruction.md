# Model Downloader — Instructions

## Overview

`download_all_models.py` is the central script for downloading all AI models required by **WalkSense AI**. It reads from `config.json` and downloads only what the current configuration needs.

### Supported Model Types

| Key     | Description                                     | Config Section                     |
| ------- | ----------------------------------------------- | ---------------------------------- |
| `yolo`  | Object detection (YOLOv8n, YOLO11m)             | `detector.models`                  |
| `vlm`   | Vision-Language Model (Qwen2-VL, Qwen3-VL, etc) | `vlm.providers.local.active_model` |
| `llm`   | Language Model (Phi-2, Phi-4-mini, etc)         | `llm.providers.local.active_model` |
| `stt`   | Speech-to-Text (Whisper small/medium/large)     | `stt.providers.local.active_model` |
| `tts`   | Text-to-Speech (Coqui TTS / pyttsx3)            | `tts.providers.local.active_model` |
| `depth` | Monocular Depth (Depth Anything V2 / MiDaS)     | `depth.active_model`               |

### Model Storage

All models are saved under `Backend/Inference/Models/`:

```
Models/
├── yolo/        # yolov8n.pt, yolo11m.pt
├── vlm/         # qwen2-vl-2b/, qwen3-vl-4b/
├── llm/         # phi-2/, phi-4-mini/
├── stt/         # whisper-small/, whisper/
├── tts/         # vits/, glow-tts/
└── depth/       # depth-anything-v2-small/
```

---

## Prerequisites

```bash
pip install -r Backend/Requirements.txt
```

Key packages: `transformers`, `ultralytics`, `faster-whisper` or `openai-whisper`, `TTS` (Coqui).

---

## Commands

### Navigate to the script directory

```bash
cd Backend/Inference/Scripts/Download_Model
```

### 1. Download All Models

Downloads every model type based on `config.json`:

```bash
python download_all_models.py
```

> **Note:** If a provider like `ollama` or `lm_studio` is set as `active_provider`, the download for that section is **skipped** (no local files needed). Use `--force` to override.

### 2. Download Only Specific Models

Download only one model type:

```bash
python download_all_models.py --only yolo
```

Download multiple specific types:

```bash
python download_all_models.py --only vlm llm
python download_all_models.py --only vlm stt depth
```

### 3. Skip Certain Models

Download everything except TTS:

```bash
python download_all_models.py --skip tts
```

Skip multiple:

```bash
python download_all_models.py --skip tts yolo
```

### 4. Force Download (Ignore Provider Check)

By default, models are only downloaded when `active_provider` is `local`, `huggingface_api`, or `coqui`. To force download regardless:

```bash
python download_all_models.py --force
```

Combine with other flags:

```bash
python download_all_models.py --only vlm llm --force
```

### 5. List All Registered Models

View all available model types without downloading anything:

```bash
python download_all_models.py --list
```

### 6. Re-download a Single Model

If a model is already downloaded, it is **skipped**. To re-download, delete its folder first:

```bash
# Example: re-download VLM
rmdir /s /q ..\..\Models\vlm\qwen2-vl-2b
python download_all_models.py --only vlm
```

On Linux/macOS:

```bash
rm -rf ../../Models/vlm/qwen2-vl-2b
python download_all_models.py --only vlm
```

---

## Switching the Active Local Model

The `local` provider for VLM, LLM, STT, and TTS uses an `active_model` key to select which model to download and use. To switch models, edit `config.json`:

### Example: Switch VLM from Qwen2-VL-2B to Qwen3-VL-4B

In `config.json`, change:

```json
"local": {
  "active_model": "qwen3-vl-4b",
  ...
}
```

Then download:

```bash
python download_all_models.py --only vlm
```

### Example: Switch LLM from Phi-2 to Phi-4-mini

```json
"local": {
  "active_model": "phi-4-mini",
  ...
}
```

```bash
python download_all_models.py --only llm
```

### Example: Switch STT from whisper-small to whisper-large-v3

```json
"local": {
  "active_model": "whisper-large-v3",
  ...
}
```

```bash
python download_all_models.py --only stt
```

---

## Provider-Aware Behavior

The script checks `active_provider` before downloading. Only these providers trigger a local download:

| Provider          | Downloads Locally? |
| ----------------- | ------------------ |
| `local`           | Yes                |
| `huggingface_api` | Yes                |
| `coqui`           | Yes                |
| `ollama`          | No (skipped)       |
| `lm_studio`       | No (skipped)       |
| `openai`          | No (skipped)       |
| `azure_openai`    | No (skipped)       |
| `bedrock`         | No (skipped)       |
| `anthropic`       | No (skipped)       |

Use `--force` to bypass this check.

---

## Common Scenarios

| Scenario                                  | Command                                                |
| ----------------------------------------- | ------------------------------------------------------ |
| First-time setup — download everything    | `python download_all_models.py`                        |
| First-time setup — force all              | `python download_all_models.py --force`                |
| Only need object detection                | `python download_all_models.py --only yolo`            |
| Need VLM + Depth, skip the rest           | `python download_all_models.py --only vlm depth`       |
| Using Ollama for LLM, skip its download   | `python download_all_models.py --skip llm`             |
| Switched VLM model in config, re-download | `python download_all_models.py --only vlm`             |
| Check what models are available           | `python download_all_models.py --list`                 |
| CI/CD — download all regardless           | `python download_all_models.py --force`                |
| Download everything except TTS and YOLO   | `python download_all_models.py --skip tts yolo`        |
| Force download only STT and LLM           | `python download_all_models.py --only stt llm --force` |

---

## Adding a New Model Type

1. Define a `download_xxx(config: dict, force: bool = False) -> bool` function in `download_all_models.py`
2. Register it in the `DOWNLOADERS` dict:
   ```python
   DOWNLOADERS = {
       ...
       "xxx": (download_xxx, "Short description"),
   }
   ```
3. (Optional) Add a config section in `config.json`
4. The `--only` / `--skip` flags will automatically pick up the new key

---

## Troubleshooting

| Issue                          | Fix                                                              |
| ------------------------------ | ---------------------------------------------------------------- |
| `transformers not installed`   | `pip install transformers accelerate`                            |
| `ultralytics not installed`    | `pip install ultralytics`                                        |
| `faster-whisper not installed` | `pip install faster-whisper` or `pip install openai-whisper`     |
| `TTS (Coqui) not installed`    | `pip install TTS`                                                |
| Download skipped unexpectedly  | Check `active_provider` in config — use `--force` to override    |
| Model already exists (skipped) | Delete the model folder and re-run, or it was already downloaded |
| Config not found               | Script expects `config.json` at `Backend/Inference/config.json`  |
