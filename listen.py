import speech_recognition as sr
import subprocess
import os
from pynput import keyboard

# Ayarlar
WORKDIR = "/Users/tony/Desktop/ark"
ARK_BIN = "/Users/tony/Desktop/ark/ark_bin"
AUDIO_PATH = "/Users/tony/Desktop/ark/assets/ark_listening.wav"


def listen_once():
    r = sr.Recognizer()
    # Hassasiyet ayarı
    r.energy_threshold = 2000

    print("ARK: Dinliyorum...")

    # 1. Sesli Onay
    if os.path.exists(AUDIO_PATH):
        subprocess.run(["afplay", AUDIO_PATH])

    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source, duration=0.8)
        try:
            # 2. Komut Bekle
            audio = r.listen(source, phrase_time_limit=5, timeout=10)

            # Ses işleme
            cmd = r.recognize_google(audio).lower()
            print(f"Komut alındı: {cmd}")

            # 3. Router Tetikleme (Binary Çağrısı)
            if "01" in cmd or "zero one" in cmd or "work" in cmd:
                print("İş Modu (01) tetikleniyor...")
                subprocess.run([ARK_BIN, "01"], cwd=WORKDIR)

            elif "02" in cmd or "zero two" in cmd or "research" in cmd:
                print("Araştırma Modu (02) tetikleniyor...")
                subprocess.run([ARK_BIN, "02"], cwd=WORKDIR)
            else:
                print(f"Komut anlaşılamadı: {cmd}")

        except Exception as e:
            print(f"Süre doldu veya hata oluştu: {e}")


# Kısayol: Cmd+Shift+Ctrl+A
with keyboard.GlobalHotKeys({"<cmd>+<shift>+<ctrl>+a": listen_once}) as h:
    print("ARK Hazır... Cmd+Shift+Ctrl+A ile çağır.")
    h.join()
