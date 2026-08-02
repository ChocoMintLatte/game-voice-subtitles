import soundcard as sc

print("=== SPEAKERS ===")
speakers = sc.all_speakers()
for i, sp in enumerate(speakers):
    print(f"Speaker {i}: {sp.name}")

print("\n=== MICROPHONES (INCLUDING LOOPBACK) ===")
try:
    mics = sc.all_microphones(include_loopback=True)
    for i, mic in enumerate(mics):
        print(f"Microphone {i}: {mic.name} (Is Loopback: {getattr(mic, 'is_loopback', False)})")
except Exception as e:
    print(f"Error getting microphones: {e}")
