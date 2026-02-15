# WalkSense – System Design Document

## 1. Architecture Overview

WalkSense follows a safety-first layered architecture separating real-time perception from contextual AI reasoning.

## 2. System Components

### Input Layer

- Camera for visual input
- Microphone for voice queries

### Perception Layer

- Real-time object detection (YOLO-based)
- Hazard identification module

### Reasoning Layer

- Vision–Language Model for scene understanding
- OCR module for text reading

### Safety Layer

- Rule-based safety engine generating priority alerts

### Orchestration Layer

- Fusion engine combining perception and reasoning outputs
- Alert prioritization controller

### Interaction Layer

- Speech-to-Text module for user queries
- Text-to-Speech module for spoken guidance

## 3. Data Flow

Camera → Object Detection → Safety Alerts  
Camera → Vision-Language Model → Scene Understanding  
OCR → Text Reading → Audio Output  
User Voice → Speech-to-Text → AI Response → Spoken Guidance

## 4. Technology Stack

- PyTorch + YOLOv8
- Vision-Language Models (Qwen-VL / LLaVA)
- OpenCV
- OCR Engines
- Whisper / SpeechRecognition (STT)
- TTS engines
- ONNX / TensorFlow Lite (edge deployment)
- FastAPI backend

## 5. Deployment Strategy

- Edge-device execution (offline capable)
- Mobile / wearable integration ready
- Scalable modular deployment
