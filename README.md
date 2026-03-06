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
- **Intelligent Scene Understanding** — Gemini VLM describes surroundings contextually
- **Natural Voice Interaction** — Ask questions via browser mic, get spoken answers
- **LLM-Powered Reasoning** — Gemini models answer user queries with scene context
- **Cloud STT Option** — Deepgram multilingual transcription (`nova-3`, `language=multi`)
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
│Camera  │ │VLM     │ │Engine  │ │STT (DG/Whsp)│
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
│   │   ├── Reasoning_Layer/       # VLM (Gemini/Qwen), LLM (Gemini/local)
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
| **API Keys**                | `GEMINI_API_KEY`, `DEEPGRAM_API_KEY`         |

### 1. Clone the Repository

```bash
git clone https://github.com/Aniket-68/WalkSense-Hackthon.git
cd WalkSense-Hackthon
```

### 2. Backend Setup

```bash
cd Backend

# Create & activate virtual environment
python3 -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Install CUDA PyTorch (GPU acceleration)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### 3. Download AI Models

```bash
cd Inference
python3 Scripts/Download_Model/download_yolo.py
```

This downloads local models needed on EC2:

- **YOLO** detection models
- **Depth** estimation models (if enabled)

### 4. Frontend Setup

```bash
cd Frontend
npm install
```

### 5. Configure API Keys

```bash
cd Backend
cp .env.example .env
```

Set:
- `GEMINI_API_KEY`
- `DEEPGRAM_API_KEY`
- `JWT_ACCESS_SECRET`
- `JWT_REFRESH_SECRET`
- `AUTH_BOOTSTRAP_USERNAME`
- `AUTH_BOOTSTRAP_PASSWORD`

### 6. Launch

```bash
# Terminal 1 — Backend (from Backend/ directory)
python3 -m API.server           # Starts on http://localhost:8080

# Terminal 2 — Frontend (from Frontend/ directory)
npm run dev                     # Starts on http://localhost:5173
```

Open **http://localhost:5173** in your browser. Click **Start** to begin the pipeline.

### Authentication

The dashboard now requires login.

1. Configure auth env in `Backend/.env`:
   - `JWT_ACCESS_SECRET`, `JWT_REFRESH_SECRET`
   - `AUTH_BOOTSTRAP_USERNAME`, `AUTH_BOOTSTRAP_PASSWORD` (dev only)
2. For managed provisioning, disable bootstrap and create users via:
   - `AUTH_BOOTSTRAP_ENABLED=false`
   - `python3 -m API.provision_user --username <user> --password '<strong-password>'`
3. In production:
   - `APP_ENV=production` (forces secure refresh cookies)
   - Set `AUTH_COOKIE_CROSS_SITE=true` only when cross-site cookies are required.
4. Sign in from the frontend login screen.
5. Access tokens are short-lived and refreshed automatically.
6. Logout revokes the full token family.
7. Login/refresh endpoints are rate-limited against brute-force attacks.
8. Auth housekeeping runs periodically to prune old audit/rate-limit rows:
   - `AUTH_HOUSEKEEPING_ENABLED=true`
   - `AUTH_CLEANUP_INTERVAL_SECONDS=3600`
   - `AUTH_AUDIT_RETENTION_SECONDS=2592000`
   - `AUTH_RATE_LIMIT_RETENTION_SECONDS=86400`
9. Monitoring hooks:
   - Prometheus-style auth metrics: `GET /metrics/auth`
   - Repeated compromise alert threshold:
     - `AUTH_ALERT_WINDOW_SECONDS`
     - `AUTH_ALERT_COMPROMISE_THRESHOLD`
     - `AUTH_ALERT_COOLDOWN_SECONDS`
     - Optional CloudWatch metrics via `AUTH_ALERT_CLOUDWATCH_ENABLED=true`

---

## CI

- GitHub Actions workflow: `.github/workflows/auth-integration.yml`
- Runs `Backend/tests/test_auth_integration.py` on push/PR changes under `Backend/**`
- Uses lightweight deps from `Backend/requirements-auth-tests.txt`

---

## ⚙️ Configuration

All settings are in [`Backend/Inference/config.json`](Backend/Inference/config.json):

### AI Providers

Each AI component supports **multiple providers** — switch by changing `active_provider`:

| Component    | Providers                                                                     | Default       |
| ------------ | ----------------------------------------------------------------------------- | ------------- |
| **VLM**      | Gemini, LM Studio, Ollama, Local HuggingFace, OpenAI, Azure, AWS Bedrock, Anthropic | `gemini` |
| **LLM**      | Gemini, Ollama, LM Studio, Local HuggingFace, OpenAI, Azure, AWS Bedrock, Together AI | `gemini` |
| **STT**      | Deepgram, Local Whisper (faster-whisper), OpenAI, Google, Azure, AWS           | `deepgram`    |
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

## ☁️ EC2 Deployment (Gemini + Deepgram)

Use this profile to run YOLO + pipeline on EC2 and keep camera on browser clients:

1. EC2 requirements:
   - Ubuntu 22.04+
   - NVIDIA driver + CUDA (for YOLO GPU)
   - Open ports: `8080` (backend), `5173` (if serving Vite dev), `443` (recommended with reverse proxy)
2. Backend on EC2:
   - `camera.mode = "browser"` in `Backend/Inference/config.json`
   - `stt.active_provider = "deepgram"`
   - `vlm.active_provider = "gemini"` with `model_id = "gemini-2.5-flash"`
   - `llm.active_provider = "gemini"` with `model_id = "gemini-2.5-flash-lite"`
3. Frontend:
   - Set `VITE_API_URL` to your EC2/API domain
   - Keep `VITE_CAMERA_MODE=browser`

Quick backend run on EC2:

```bash
cd Backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 -m API.server
```

For production, use included service template:

```bash
sudo cp Backend/deploy/ec2/walksense-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now walksense-backend
```

For internet access, place Nginx/ALB in front of port `8080` and terminate HTTPS.

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
| `POST` | `/api/auth/login`   | Login with username/password           |
| `POST` | `/api/auth/refresh` | Rotate refresh token and get new access|
| `POST` | `/api/auth/logout`  | Revoke token family and logout         |
| `POST` | `/api/auth/revoke-family` | Emergency revoke for current session |
| `GET`  | `/api/auth/me`      | Get current authenticated user         |
| `POST` | `/api/system/start` | Start the AI pipeline                  |
| `POST` | `/api/system/stop`  | Stop the AI pipeline                   |
| `GET`  | `/api/system/status`| Current pipeline state (JSON)          |
| `POST` | `/api/voice-query`  | Upload audio → transcribe → query submit |
| `POST` | `/api/query`        | Send text query                        |
| `GET`  | `/api/camera/feed`  | MJPEG video stream                     |
| `WS`   | `/ws`               | Real-time pipeline state updates       |
| `WS`   | `/ws/camera`        | Browser camera frame ingestion         |

All non-auth endpoints are protected by bearer access JWT.
Refresh tokens are HttpOnly cookies and rotated on `/api/auth/refresh`.

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

### Gemini VLM/LLM Not Responding

1. Ensure `GEMINI_API_KEY` is set in `Backend/.env`
2. Confirm model IDs in `config.json`:
   - `gemini-2.5-flash` (VLM)
   - `gemini-2.5-flash-lite` (LLM)
3. Check backend logs for `[VLM] Gemini` or `[LLM]` errors

### STT Not Transcribing / Clipping Words

1. Ensure FFmpeg is installed: `ffmpeg -version`
2. Allow microphone access in your browser
3. Ensure `DEEPGRAM_API_KEY` is set and check `[STT] Deepgram` logs

### Frontend Can't Connect

1. Verify backend is running on port **8080**
2. Check CORS — backend allows all origins by default
3. Check browser console for WebSocket errors

---

## 🔒 Privacy & Security

- **Hybrid Processing** — Detection/depth local on EC2, optional cloud reasoning/STT
- **Configurable Providers** — Switch between local and API providers via `config.json`
- **No Storage** — Video frames are processed in memory, never saved to disk
- **Optional Cloud** — Gemini and Deepgram are enabled by default in this profile

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
