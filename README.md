# WalkSense 🚶‍♂️👁️

> AI-Powered Real-Time Assistive Navigation System for Visually Impaired Users

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![React](https://img.shields.io/badge/React-19.2-61DAFB?logo=react&logoColor=white)](https://react.dev/)
[![PyTorch](https://img.shields.io/badge/PyTorch_2.5-CUDA_12.1-%23EE4C2C.svg?logo=PyTorch&logoColor=white)](https://pytorch.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

WalkSense is a real-time AI assistant that combines **computer vision**, **depth estimation**, **vision-language models**, and **natural language processing** to help visually impaired users navigate safely and interact with their environment through voice. It features a **React dashboard** for monitoring and a **FastAPI backend** that orchestrates the full AI pipeline.

---

## 🌟 Key Features

- **Real-time Object Detection** — YOLO v8/v11 with CUDA acceleration
- **Monocular Depth Estimation** — MiDaS / Depth Anything V2 for spatial awareness
- **Intelligent Scene Understanding** — Qwen VLM describes surroundings contextually
- **Natural Voice Interaction** — Ask questions via browser mic, get spoken answers
- **LLM-Powered Reasoning** — Gemma / Phi models answer user queries with scene context
- **Multi-tier Safety Alerts** — Critical hazards trigger immediate voice warnings
- **Browser Camera Mode** — Stream camera from any device (supports cloud/EC2 deployment)
- **Live Dashboard** — React + Vite frontend with real-time pipeline monitoring
- **Multi-provider Support** — LM Studio, Ollama, HuggingFace, OpenAI, Azure, AWS, and more
- **Privacy-First** — Fully local processing by default, no cloud required

---

## 🏗️ Architecture

WalkSense uses a **layered architecture** with a FastAPI server orchestrating all components:

```
┌──────────────────────────────────────────────────┐
│              REACT FRONTEND (Vite)               │
│   Dashboard · Camera Feed · Voice Query · Logs   │
└────────────────────┬─────────────────────────────┘
                     │ REST + WebSocket
┌────────────────────▼─────────────────────────────┐
│           FastAPI SERVER (port 8080)             │
│         SystemManager · Pipeline Loop            │
└──┬──────────┬──────────┬──────────┬──────────────┘
   ▼          ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌─────────────┐
│PERCEPT.│ │REASON. │ │FUSION  │ │INTERACTION  │
│Camera  │ │VLM     │ │Engine  │ │STT (Whisper)│
│YOLO    │ │LLM     │ │Router  │ │TTS (pyttsx3)│
│Depth   │ │        │ │State   │ │Audio Worker │
│Alerts  │ │        │ │Context │ │Haptics/LED  │
└────────┘ └────────┘ └────────┘ └─────────────┘
   ▼          ▼          ▼          ▼
┌──────────────────────────────────────────────────┐
│             INFRASTRUCTURE                       │
│   Config · Metrics · Performance · Sampler       │
└──────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
WalkSense-Hackthon/
├── Backend/
│   ├── API/
│   │   ├── server.py              # FastAPI server (REST + WebSocket + MJPEG)
│   │   └── manager.py             # SystemManager — pipeline orchestrator
│   ├── Inference/
│   │   ├── config.json            # All system configuration
│   │   ├── Perception_Layer/      # Camera, YOLO detector, depth, safety rules
│   │   ├── Reasoning_Layer/       # VLM (Qwen), LLM (Gemma/Phi)
│   │   ├── Fusion_Layer/          # Orchestration, routing, state, context
│   │   ├── Interaction_Layer/     # STT, TTS, audio, haptics, buzzer, LED
│   │   ├── Infrastructure/        # Config loader, metrics, performance, sampler
│   │   ├── Models/                # Downloaded AI model weights (git-ignored)
│   │   ├── Scripts/               # Setup, model downloads, testing utilities
│   │   └── Logs/                  # Runtime logs
│   └── Requirements.txt           # Python dependencies
├── Frontend/
│   ├── src/
│   │   ├── App.jsx                # Main app layout
│   │   ├── components/
│   │   │   ├── CameraFeed.jsx     # MJPEG camera display
│   │   │   ├── BrowserCamera.jsx  # getUserMedia → WebSocket streaming
│   │   │   ├── QueryDisplay.jsx   # Voice query recording & dialogue
│   │   │   ├── PipelineMonitor.jsx# Real-time pipeline state
│   │   │   ├── SystemControls.jsx # Start/Stop/Mute controls
│   │   │   └── KeyboardShortcuts.jsx
│   │   └── hooks/
│   │       └── useWebSocket.js    # WebSocket connection hook
│   ├── package.json
│   └── vite.config.js
├── Docs/                          # Architecture & metrics documentation
├── Design.md                      # System design document
├── Requirements.md                # Functional requirements
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites

| Requirement                 | Details                                      |
| --------------------------- | -------------------------------------------- |
| **Python**                  | 3.10+                                        |
| **Node.js**                 | 18+ (for frontend)                           |
| **CUDA GPU**                | Recommended (RTX 3060+ for best performance) |
| **FFmpeg**                  | Required for audio processing                |
| **LM Studio** or **Ollama** | For VLM/LLM inference                        |

### 1. Clone the Repository

```bash
git clone https://github.com/Aniket-68/WalkSense-Hackthon.git
cd WalkSense-Hackthon
```

### 2. Backend Setup

```bash
cd Backend

# Create & activate virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac

# Install dependencies
pip install -r Requirements.txt

# Install CUDA PyTorch (GPU acceleration)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### 3. Download AI Models

```bash
cd Inference
python Scripts/setup_project.py

# Or download individual models:
python Scripts/Download_Model/download_yolo.py
```

This downloads:

- **YOLO** detection models (YOLOv8n, YOLO11m)
- **Whisper** speech recognition (small/medium/large)
- **Depth** estimation (MiDaS, Depth Anything V2)
- **VLM/LLM** weights (if using local providers)

### 4. Frontend Setup

```bash
cd Frontend
npm install
```

### 5. Start External AI Services

**Option A — LM Studio (recommended for VLM):**

1. Download [LM Studio](https://lmstudio.ai/)
2. Load `Qwen3-VL-4B` (or any vision-capable model)
3. Start server on port **1234**

**Option B — Ollama (recommended for LLM):**

```bash
ollama pull gemma3:270m
ollama serve                    # Runs on port 11434
```

### 6. Launch

```bash
# Terminal 1 — Backend (from Backend/ directory)
python -m API.server            # Starts on http://localhost:8080

# Terminal 2 — Frontend (from Frontend/ directory)
npm run dev                     # Starts on http://localhost:5173
```

Open **http://localhost:5173** in your browser. Click **Start** to begin the pipeline.

---

## ⚙️ Configuration

All settings are in [`Backend/Inference/config.json`](Backend/Inference/config.json):

### AI Providers

Each AI component supports **multiple providers** — switch by changing `active_provider`:

| Component    | Providers                                                                     | Default       |
| ------------ | ----------------------------------------------------------------------------- | ------------- |
| **VLM**      | LM Studio, Ollama, Local HuggingFace, OpenAI, Azure, AWS Bedrock, Anthropic   | `lm_studio`   |
| **LLM**      | Ollama, LM Studio, Local HuggingFace, OpenAI, Azure, AWS Bedrock, Together AI | `ollama`      |
| **STT**      | Local Whisper (faster-whisper), OpenAI, Google, Azure, AWS                    | `local`       |
| **TTS**      | pyttsx3, Coqui, OpenAI, Google, Azure, AWS Polly                              | `local`       |
| **Depth**    | MiDaS Small/Large, Depth Anything V2 Small/Base                               | `midas_small` |
| **Detector** | YOLOv8n, YOLO11m, Custom fine-tuned                                           | `yolo11m`     |

### Camera Modes

```jsonc
"camera": {
  "mode": "hardware"    // "hardware" | "simulation" | "browser"
}
```

- **hardware** — USB/built-in camera via OpenCV
- **simulation** — Loop a video file for testing
- **browser** — Frontend streams camera via WebSocket (ideal for cloud/EC2 deployment)

---

## 🎮 Usage

### Dashboard Controls

| Button              | Action                                 |
| ------------------- | -------------------------------------- |
| **Start / Stop**    | Toggle the AI pipeline                 |
| **🎤 Hold to Talk** | Record voice query and send to backend |
| **Mute**            | Toggle audio output                    |

### Voice Interaction Examples

Hold the microphone button and speak:

```
You:       "What do you see in front of me?"
WalkSense: "I see a person standing about 2 meters ahead wearing a blue jacket,
            and a wooden bench to your right."

You:       "Is it safe to cross?"
WalkSense: "I can see a car approaching from the left. Please wait."
```

### Automatic Safety Alerts

The system continuously monitors and announces hazards:

| Priority        | Example                                                   |
| --------------- | --------------------------------------------------------- |
| 🔴 **Critical** | _"Danger! Car detected ahead. Stop immediately."_         |
| 🟡 **Warning**  | _"Warning! Pole ahead at 1.5 meters. Proceed carefully."_ |
| 🟢 **Info**     | _"Chair detected to your left."_                          |

---

## 🔌 API Reference

The FastAPI backend exposes these endpoints:

| Method | Endpoint            | Description                            |
| ------ | ------------------- | -------------------------------------- |
| `POST` | `/api/system/start` | Start the AI pipeline                  |
| `POST` | `/api/system/stop`  | Stop the AI pipeline                   |
| `GET`  | `/api/system/state` | Current pipeline state (JSON)          |
| `POST` | `/api/voice-query`  | Upload audio → transcribe → LLM answer |
| `POST` | `/api/text-query`   | Send text query → LLM answer           |
| `GET`  | `/api/camera/feed`  | MJPEG video stream                     |
| `WS`   | `/ws`               | Real-time pipeline state updates       |
| `WS`   | `/ws/camera`        | Browser camera frame ingestion         |

---

## ⚡ Performance

### Expected Latency (CUDA GPU)

| Component            | RTX 4060  | CPU (i7)    |
| -------------------- | --------- | ----------- |
| YOLO Detection       | ~300ms    | ~800ms      |
| Depth Estimation     | ~100ms    | ~500ms      |
| VLM Description      | ~2-3s     | ~8-10s      |
| STT (Whisper small)  | ~500ms    | ~2-3s       |
| LLM Reasoning        | ~1-2s     | ~3-5s       |
| **End-to-End Query** | **~5-8s** | **~15-20s** |

### Optimization Tips

1. **Use smaller models** — YOLOv8n, Whisper small, Gemma3:270m
2. **Adjust VLM sampling** — `perception.sampling_interval` controls how often VLM runs (default: every 150 frames)
3. **Enable redundancy filtering** — `safety.suppression.enabled: true` avoids repeating alerts
4. **GPU for all components** — Set `"device": "cuda"` in detector, STT, and depth configs

---

## 🐛 Troubleshooting

### CUDA Not Available

```bash
pip uninstall torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

Verify: `python -c "import torch; print(torch.cuda.is_available())"`

### VLM Not Responding

1. Ensure **LM Studio** is running with a vision model loaded
2. Check the server URL: `curl http://localhost:1234/v1/models`
3. Or switch to Ollama: set `vlm.active_provider` to `"ollama"` in config

### STT Not Transcribing / Clipping Words

1. Ensure FFmpeg is installed: `ffmpeg -version`
2. Allow microphone access in your browser
3. Check logs for `[STT]` messages in the backend terminal

### Frontend Can't Connect

1. Verify backend is running on port **8080**
2. Check CORS — backend allows all origins by default
3. Check browser console for WebSocket errors

---

## 🔒 Privacy & Security

- **Local-First** — All processing runs on-device by default
- **No Telemetry** — Zero data collection or external communication
- **No Storage** — Video frames are processed in memory, never saved to disk
- **Optional Cloud** — Users can opt-in to cloud APIs (OpenAI, Azure, AWS) via config

---

## 🤝 Contributing

1. **Layer Separation** — Keep perception, reasoning, and interaction decoupled
2. **Configuration-Driven** — Add tunable parameters to `config.json`
3. **Type Safety** — Include type hints and docstrings
4. **Logging** — Use `loguru` for structured logging
5. **Performance** — Track latency for any new pipeline operations

---

## 🙏 Acknowledgments

Built with:

- [Ultralytics YOLO](https://github.com/ultralytics/ultralytics) — Object detection
- [faster-whisper](https://github.com/guillaumekln/faster-whisper) — Speech recognition
- [Qwen-VL](https://huggingface.co/Qwen) — Vision-language understanding
- [LM Studio](https://lmstudio.ai/) / [Ollama](https://ollama.com/) — Local LLM inference
- [MiDaS](https://github.com/isl-org/MiDaS) / [Depth Anything](https://github.com/DepthAnything/Depth-Anything-V2) — Depth estimation
- [FastAPI](https://fastapi.tiangolo.com/) — Backend API server
- [React](https://react.dev/) + [Vite](https://vite.dev/) — Frontend dashboard
- [loguru](https://github.com/Delgan/loguru) — Logging

---

## 📝 License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

## 📧 Contact

- **GitHub Issues**: [github.com/Aniket-68/WalkSense-Hackthon/issues](https://github.com/Aniket-68/WalkSense-Hackthon/issues)
- **Email**: aniketchauhan0608@gmail.com

---

**Made with ❤️ for accessible technology**
