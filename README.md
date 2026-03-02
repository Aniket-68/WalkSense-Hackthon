# WalkSense 🚶‍♂️👁️

> AI-Powered Assistive Navigation System for Visually Impaired Users

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyTorch](https://img.shields.io/badge/PyTorch-%23EE4C2C.svg?logo=PyTorch&logoColor=white)](https://pytorch.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

WalkSense is a real-time AI assistant that combines computer vision, natural language processing, and spatial awareness to help visually impaired users navigate safely and interact with their environment through voice.

![WalkSense Architecture](docs/architecture_diagram.png)

## 🌟 Key Features

- **Real-time Object Detection**: YOLO-based detection at 30 FPS
- **Intelligent Scene Understanding**: Vision-language models describe surroundings
- **Natural Voice Interaction**: Ask questions, get instant answers
- **Multi-tier Safety Alerts**: Critical hazards trigger immediate warnings
- **Spatial Awareness**: Tracks objects across time and space
- **Multi-modal Feedback**: Voice + haptic + LED/buzzer notifications
- **Privacy-First**: 100% local processing, no cloud required

## 🏗️ Architecture

WalkSense uses a **layered architecture** for modularity and extensibility:

```
┌─────────────────────────────────────────┐
│       INTERACTION LAYER                 │
│   (Voice I/O, Haptics, Audio)           │
└───────────────┬─────────────────────────┘
                ↓
┌─────────────────────────────────────────┐
│        FUSION LAYER                     │
│   (Orchestration, Routing, State)       │
└───────┬─────────────────┬───────────────┘
        ↓                 ↓
┌───────────────┐  ┌──────────────────────┐
│  PERCEPTION   │  │   REASONING LAYER    │
│  (YOLO, Cam)  │  │  (VLM, LLM)          │
└───────────────┘  └──────────────────────┘
        ↓                 ↓
┌─────────────────────────────────────────┐
│       INFRASTRUCTURE                    │
│   (Config, Perf Tracking, Utils)        │
└─────────────────────────────────────────┘
```

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed layer descriptions.

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **CUDA-capable GPU** (recommended for best performance)
- **Microphone** for voice input
- **Speakers** for audio output

### Installation

1. **Clone the repository**:
```bash
git clone https://github.com/yourusername/WalkSense.git
cd WalkSense
```

2. **Run automated setup** (Windows):
```bash
setup.bat
```

Or manually:
```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Install CUDA PyTorch (for GPU acceleration)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

3. **Download AI models**:
```bash
python scripts/setup_project.py
```

This will download:
- YOLO detection models (YOLOv8n, YOLO11m)
- Whisper speech recognition models
- Configuration templates

### Configuration

Edit `config.json` to customize:

```json
{
  "vlm": {
    "active_provider": "lm_studio",  // or "huggingface", "ollama"
    "providers": { ... }
  },
  "llm": {
    "active_provider": "ollama",  // For query answering
    "providers": { ... }
  },
  "detector": {
    "device": "cuda",  // Use GPU acceleration
    "active_model": "yolov8n"
  },
  "stt": {
    "active_provider": "whisper_local"  // Local Whisper
  }
}
```

### Start LM Studio (for VLM)

1. Download [LM Studio](https://lmstudio.ai/)
2. Load a vision-capable model (e.g., `Qwen2-VL-2B`)
3. Start server on port 1234

### Launch WalkSense

```bash
python -m scripts.run_enhanced_camera
```

## 🎮 Usage

### Keyboard Controls

- **`S`**: Start/Resume system
- **`L`**: Ask a question (triggers voice input)
- **`M`**: Mute/Unmute audio
- **`Q`**: Quit application

### Voice Interaction

**Press `L`** and speak your question:

```
User: "What's in front of me?"
WalkSense: "A person standing 2 meters ahead with a blue backpack"

User: "Is there a chair nearby?"
WalkSense: "Yes, a brown chair to your left"

User: "Can I cross the street?"
WalkSense: "Wait! I see a car approaching from the right"
```

### Safety Alerts

The system automatically announces hazards:

- **Critical**: `"Danger! Car detected ahead. Stop immediately."`
- **Warning**: `"Warning! Pole ahead. Proceed carefully."`
- **Info**: `"Chair nearby"`

## 📖 Documentation

- **[Architecture Guide](ARCHITECTURE.md)**: System design and data flow
- **[Performance Metrics](docs/PERFORMANCE_METRICS.md)**: Comprehensive performance benchmarks
- **[Quality Metrics](docs/QUALITY_METRICS.md)**: User experience and quality analysis
- **[Latency Analysis](docs/LATENCY.md)**: Detailed latency breakdown and optimization
- **[Configuration Guide](ENHANCED_SYSTEM.md)**: Detailed config options
- **[Performance Tuning](#performance-optimization)**: Optimize for your hardware

## 🛠️ Development

### Project Structure

```
WalkSense/
├── perception_layer/       # Camera, YOLO, safety rules
├── reasoning_layer/        # VLM, LLM AI models
├── fusion_layer/          # Central orchestration
├── interaction_layer/     # Voice, audio, haptics
├── infrastructure/        # Config, logging, utils
├── scripts/              # Entry points, setup
├── models/               # Downloaded AI weights
├── config.json           # System configuration
└── docs/                 # Documentation
```

### Adding Features

#### New STT Provider

1. Add config to `config.json`:
```json
"stt": {
  "providers": {
    "my_provider": {
      "api_key": "...",
      "model": "..."
    }
  }
}
```

2. Implement in `interaction_layer/stt.py`:
```python
def _recognize_my_provider(self, audio):
    # Your implementation
    return transcribed_text
```

#### New Safety Rule

Edit `perception_layer/rules.py`:
```python
CRITICAL_OBJECTS = {
    "knife", "gun", "fire",
    "my_new_hazard"  # Add here
}
```

## ⚡ Performance Optimization

### GPU Acceleration

Enable CUDA for all components:

```json
{
  "detector": { "device": "cuda" },
  "stt": { "providers": { "whisper_local": { "device": "cuda" } } }
}
```

### Latency Reduction

1. **Use smaller models**:
   - YOLOv8n instead of YOLO11m
   - Whisper base instead of large
   - Smaller LLM (Gemma3:270m, Phi-4)

2. **Adjust sampling**:
```json
"perception": {
  "sampling_interval": 150  // Run VLM every 150 frames (~5s)
}
```

3. **Enable redundancy filtering**:
```json
"safety": {
  "suppression": {
    "enabled": true,
    "redundancy_threshold": 0.6
  }
}
```

### Expected Performance

| Component | GPU (RTX 4060) | CPU (i7) |
|-----------|----------------|----------|
| YOLO Detection | ~300ms | ~800ms |
| VLM Description | ~2-3s | ~8-10s |
| STT (Whisper) | ~500ms | ~2-3s |
| LLM Reasoning | ~1-2s | ~3-5s |
| **End-to-End Query** | ~5-8s | ~15-20s |

## 🐛 Troubleshooting

### CUDA Not Available

```bash
pip uninstall torch
pip install torch --index-url https://download.pytorch.org/whl/cu124
```

### STT Not Working

1. Check microphone permissions
2. List available mics: `python scripts/check_mics.py`
3. Update `config.json` with correct mic ID:
```json
"microphone": { "hardware": { "id": 2 } }
```

### VLM Connection Failed

1. Ensure LM Studio is running
2. Verify model is loaded
3. Check port (default: 1234)
4. Test: `curl http://localhost:1234/v1/models`

### Audio Not Playing

Check `interaction_layer/audio_worker.py` path in logs.

## 📊 Monitoring

### Performance Logs

```bash
# View real-time performance
tail -f logs/performance.log

# Generate visualization (on exit)
# Creates: plots/performance_summary.png
```

### Metrics Tracked

- Frame processing time
- YOLO inference latency
- VLM description time
- LLM reasoning time
- STT transcription speed

## 🤝 Contributing

Contributions welcome! Key principles:

1. **Layer Separation**: Keep perception, reasoning, and interaction decoupled
2. **Configuration-Driven**: Use `config.json` for tunable parameters
3. **Type Safety**: Include type hints and docstrings
4. **Logging**: Use `loguru` for all output
5. **Performance**: Track latency for major operations

See [API_REFERENCE.md](docs/API_REFERENCE.md) for development guidelines.

## 🔒 Privacy & Security

- **Local-First**: All processing runs on-device by default
- **No Telemetry**: No data collection or external communication
- **No Storage**: Video frames are not saved
- **Optional Cloud**: Users can opt-in to cloud APIs (OpenAI Whisper, etc.)

## 📝 License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

Built with:
- [Ultralytics YOLO](https://github.com/ultralytics/ultralytics) - Object detection
- [faster-whisper](https://github.com/guillaumekln/faster-whisper) - Speech recognition
- [Qwen2-VL](https://huggingface.co/Qwen) - Vision-language understanding
- [LM Studio](https://lmstudio.ai/) - Local LLM inference
- [loguru](https://github.com/Delgan/loguru) - Logging

## 📧 Contact

For questions or feedback:
- **GitHub Issues**: [github.com/Aniket-68/WalkSense/issues](https://github.com/Aniket-68/WalkSense/issues)
- **Email**: aniketchauhan0608@gmail.com

---

**Made with ❤️ for accessible technology**
