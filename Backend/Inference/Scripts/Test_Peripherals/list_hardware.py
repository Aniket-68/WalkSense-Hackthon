import speech_recognition as sr
import cv2

def list_microphones():
    print("Scanning Microphones...")
    mics = sr.Microphone.list_microphone_names()
    results = []
    results.append("=== MICROPHONES ===")
    for index, name in enumerate(mics):
        line = f"ID {index}: {name}"
        results.append(line)
        print(line)
    return results

def list_cameras():
    print("\nScanning Cameras (First 10 indices)...")
    results = []
    results.append("\n=== CAMERAS ===")
    for index in range(10):
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                line = f"ID {index}: Available"
                results.append(line)
                print(line)
            cap.release()
    return results

if __name__ == "__main__":
    mic_info = list_microphones()
    cam_info = list_cameras()
    
    with open("HARDWARE_INFO.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(mic_info))
        f.write("\n")
        f.write("\n".join(cam_info))
    
    print("\nInfo saved to HARDWARE_INFO.txt")
