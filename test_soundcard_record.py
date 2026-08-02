import soundcard as sc
import wave
import numpy as np
import time

# Get default speaker
default_speaker = sc.default_speaker()
print(f"Default Speaker: {default_speaker.name}")

# Get loopback microphone associated with default speaker
mics = sc.all_microphones(include_loopback=True)
loopback_mic = None
for mic in mics:
    if mic.name == default_speaker.name:
        loopback_mic = mic
        break

if not loopback_mic:
    for mic in mics:
        if default_speaker.name in mic.name or mic.name in default_speaker.name:
            loopback_mic = mic
            break

if not loopback_mic:
    print("Error: Could not find loopback mic for default speaker.")
    exit(1)

print(f"Recording 5 seconds from loopback microphone: {loopback_mic.name}")

samplerate = 48000
try:
    with loopback_mic.recorder(samplerate=samplerate, channels=2) as recorder:
        data = recorder.record(numframes=samplerate * 5)
except Exception as e:
    print(f"Record failed: {e}")
    exit(1)

print("Recording finished.")
print(f"Recorded shape: {data.shape}")
print(f"Min: {np.min(data)}, Max: {np.max(data)}")
print(f"RMS: {np.sqrt(np.mean(data**2))}")

# Convert to mono & resample to 16000Hz
mono = np.mean(data, axis=1)
duration = len(mono) / samplerate
num_target_samples = int(duration * 16000)
x_orig = np.linspace(0, duration, len(mono))
x_target = np.linspace(0, duration, num_target_samples)
resampled = np.interp(x_target, x_orig, mono)

# Convert to int16
clipped = np.clip(resampled, -1.0, 1.0)
audio_int16 = (clipped * 32767).astype(np.int16)

# Save to wav
with wave.open("test_soundcard_record.wav", "wb") as wav_file:
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)
    wav_file.setframerate(16000)
    wav_file.writeframes(audio_int16.tobytes())

print("Saved to test_soundcard_record.wav.")
