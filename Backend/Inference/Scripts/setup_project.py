# scripts/setup_project.py
import os
import sys
import subprocess
import json
import shutil

def run_command(command, cwd=None, capture_output=False):
    """Run a shell command and return its exit code or output."""
    try:
        if capture_output:
            result = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True)
            return result.returncode, result.stdout.strip()
        else:
            process = subprocess.Popen(command, shell=True, cwd=cwd)
            process.wait()
            return process.returncode
    except Exception as e:
        print(f"Error running command: {e}")
        return 1 if not capture_output else (1, str(e))

def setup_venv():
    """Create virtual environment if it doesn't exist."""
    if not os.path.exists("venv"):
        print("[SETUP] Creating virtual environment...")
        run_command(f"{sys.executable} -m venv venv")
        print("[OK] Virtual environment created.")
    else:
        print("[SETUP] Virtual environment already exists.")

def get_venv_bin():
    """Returns path to python and pip in venv."""
    if os.name == "nt":
        return os.path.join("venv", "Scripts", "python.exe"), os.path.join("venv", "Scripts", "pip.exe")
    else:
        return os.path.join("venv", "bin", "python"), os.path.join("venv", "bin", "pip")

def install_requirements():
    """Install dependencies from requirements.txt."""
    print("[SETUP] Installing requirements...")
    python_path, pip_path = get_venv_bin()
    
    if os.path.exists("requirements.txt"):
        run_command(f"{pip_path} install --upgrade pip")
        run_command(f"{pip_path} install -r requirements.txt")
        print("[OK] Requirements updated.")
    else:
        print("[ERROR] requirements.txt not found!")

def load_config():
    """Loads configuration from config.json"""
    config_path = "config.json"
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    return {}

def download_yolo_logic(python_path, config):
    """Consolidated YOLO download logic pull from config.json."""
    print("[YOLO] Checking YOLO models...")
    
    yolo_config = config.get("detector", {})
    models_dict = yolo_config.get("models", {
        "yolov8n": "models/yolo/yolov8n.pt",
        "yolo11m": "models/yolo/yolo11m.pt"
    })
    
    target_dir = "models/yolo"
    os.makedirs(target_dir, exist_ok=True)
    
    for model_alias, target_path in models_dict.items():
        # Alias like 'yolo11m' might not have .pt, check logic
        model_name = f"{model_alias}.pt" if not model_alias.endswith(".pt") else model_alias
        
        if not os.path.exists(target_path):
            print(f"[YOLO] Downloading {model_name}...")
            # Use ultralytics to download
            cmd = f'{python_path} -c "from ultralytics import YOLO; import shutil; model = YOLO(\'{model_name}\'); import os; if os.path.exists(\'{model_name}\'): shutil.move(\'{model_name}\', \'{target_path}\')"'
            run_command(cmd)
            print(f"[OK] {model_name} ready.")
        else:
            print(f"[SKIP] {model_alias} already exists at {target_path}.")

def download_whisper_logic(python_path, config):
    """Consolidated Whisper download logic pull from config.json."""
    print("[WHISPER] Checking Whisper models...")
    stt_config = config.get("stt", {}).get("providers", {}).get("whisper_local", {})
    model_size = stt_config.get("model_size", "base")
    
    target_dir = "models/whisper"
    os.makedirs(target_dir, exist_ok=True)
    
    # 1. Standard Whisper
    model_file = os.path.join(target_dir, f"{model_size}.pt")
    if not os.path.exists(model_file):
        print(f"[WHISPER] Downloading Whisper {model_size}...")
        cmd = f'{python_path} -c "import whisper; whisper.load_model(\'{model_size}\', download_root=\'{target_dir}\')"'
        run_command(cmd)
    else:
        print(f"[SKIP] Whisper {model_size} already exists.")
        
    # 2. Faster Whisper
    print(f"[WHISPER] Checking Faster Whisper {model_size}...")
    cmd = f'{python_path} -c "from faster_whisper import WhisperModel; WhisperModel(\'{model_size}\', device=\'cpu\', compute_type=\'int8\', download_root=\'{target_dir}\')"'
    run_command(cmd)

def pull_ollama_model(model_name):
    """Pulls model via Ollama CLI."""
    print(f"[OLLAMA] Pulling model: {model_name}...")
    code, version = run_command("ollama --version", capture_output=True)
    if code == 0:
        run_command(f"ollama pull {model_name}")
        print(f"[OK] {model_name} pulled.")
    else:
        print(f"[WARNING] Ollama CLI not found. Skipping pull for {model_name}.")

def download_hf_model(python_path, model_id, is_vlm=True):
    """Downloads Hugging Face model using the venv's python."""
    print(f"[HF] Checking Hugging Face model: {model_id}...")
    
    if is_vlm:
        # VLM download (Qwen2-VL)
        cmd = f'{python_path} -c "from transformers import Qwen2VLForConditionalGeneration, AutoProcessor; ' \
              f'print(\'Downloading VLM {model_id}...\'); ' \
              f'AutoProcessor.from_pretrained(\'{model_id}\'); ' \
              f'Qwen2VLForConditionalGeneration.from_pretrained(\'{model_id}\', torch_dtype=\'auto\', device_map=\'auto\'); ' \
              f'print(\'VLM Ready\')"'
    else:
        # Standard LLM download
        cmd = f'{python_path} -c "from transformers import AutoModelForCausalLM, AutoTokenizer; ' \
              f'print(\'Downloading LLM {model_id}...\'); ' \
              f'AutoTokenizer.from_pretrained(\'{model_id}\'); ' \
              f'AutoModelForCausalLM.from_pretrained(\'{model_id}\'); ' \
              f'print(\'LLM Ready\')"'
    
    run_command(cmd)

def main():
    # Ensure correctly in project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(script_dir, ".."))
    os.chdir(root_dir)
    
    print("\n=========================================")
    print("WalkSense - Master Setup & Downloader")
    print("=========================================")
    
    # 1. Virtual Environment
    setup_venv()
    
    # 2. Dependencies
    install_requirements()
    
    # Get current venv context
    python_path, _ = get_venv_bin()
    
    # 3. Load Project Config
    config = load_config()
    
    # 4. YOLO Models
    download_yolo_logic(python_path, config)
    
    # 5. Whisper Models
    download_whisper_logic(python_path, config)
    
    # 6. Dynamic VLM/LLM from config
    # 6.1 VLM
    vlm_provider = config.get("vlm", {}).get("active_provider")
    if vlm_provider:
        vlm_config = config["vlm"]["providers"].get(vlm_provider, {})
        model_id = vlm_config.get("model_id")
        print(f"[VLM] Provider: {vlm_provider} | ID: {model_id}")
        if vlm_provider == "ollama": pull_ollama_model(model_id)
        elif vlm_provider == "huggingface": download_hf_model(python_path, model_id, is_vlm=True)
        elif vlm_provider == "lm_studio": print(f"[INFO] VLM uses LM Studio. Manual download for '{model_id}' suggested in LM Studio UI.")

    # 6.2 LLM
    llm_provider = config.get("llm", {}).get("active_provider")
    if llm_provider:
        llm_config = config["llm"]["providers"].get(llm_provider, {})
        model_id = llm_config.get("model_id")
        print(f"[LLM] Provider: {llm_provider} | ID: {model_id}")
        if llm_provider == "ollama": pull_ollama_model(model_id)
        elif llm_provider == "huggingface": download_hf_model(python_path, model_id, is_vlm=False)
        elif llm_provider == "lm_studio": print(f"[INFO] LLM uses LM Studio. Manual download for '{model_id}' suggested in LM Studio UI.")

    print("\n=========================================")
    print("Setup Complete!")
    print("=========================================")
    print("\nAction Required:")
    print("1. venv\\Scripts\\activate (Windows) or source venv/bin/activate (Linux/Mac)")
    print("2. python scripts/run_enhanced_camera.py")

if __name__ == "__main__":
    main()
