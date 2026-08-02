import sounddevice as sd
import numpy as np
import wave
import time

# List WASAPI devices to find a working loopback
devices = sd.query_devices()
host_apis = sd.query_hostapis()
wasapi_idx = -1
for idx, api in enumerate(host_apis):
    if api['name'] == 'Windows WASAPI':
        wasapi_idx = idx
        break

# Find default output first
default_output = sd.query_devices(kind='output')
print(f"Default Output Device: {default_output['name']}")

# Find input loopbacks
loopback_keywords = ['loopback', '루프백', 'what u hear', 'stereo mix', '스테레오 믹스', 'wave out mix']
loopback_idx = -1
for idx, dev in enumerate(devices):
    if dev['hostapi'] == wasapi_idx and dev['max_input_channels'] > 0:
        name_lower = dev['name'].lower()
        if any(kw in name_lower for kw in loopback_keywords):
            loopback_idx = idx
            print(f"Found Loopback Device {idx}: {dev['name']}")
            break

# If not found, use first input on WASAPI
if loopback_idx == -1:
    for idx, dev in enumerate(devices):
        if dev['hostapi'] == wasapi_idx and dev['max_input_channels'] > 0:
            loopback_idx = idx
            print(f"Fallback to WASAPI Input Device {idx}: {dev['name']}")
            break

if loopback_idx == -1:
    print("Error: No WASAPI input device found.")
    exit(1)

dev_info = sd.query_devices(loopback_idx)
samplerate = int(dev_info['default_samplerate'])
channels = dev_info['max_input_channels']

print(f"\nRecording 5 seconds from device {loopback_idx} ({dev_info['name']})...")
print(f"Samplerate: {samplerate}, Channels: {channels}")

recording_buffer = []

def callback(indata, frames, time_info, status):
    if status:
        print(f"Status: {status}")
    recording_buffer.append(indata.copy())

try:
    with sd.InputStream(device=loopback_idx, channels=channels, samplerate=samplerate, callback=callback):
        time.sleep(5.0)
except Exception as e:
    print(f"Record failed: {e}")
    exit(1)

print("Recording finished.")
audio_data = np.concatenate(recording_buffer, axis=0)
print(f"Recorded shape: {audio_data.shape}")
print(f"Min value: {np.min(audio_data)}")
print(f"Max value: {np.max(audio_data)}")
print(f"RMS value: {np.sqrt(np.mean(audio_data**2))}")

# Convert to mono & resample to 16000Hz
if channels > 1:
    mono = np.mean(audio_data, axis=1)
else:
    mono = audio_data.flatten()

# Resample using interpolation
duration = len(mono) / samplerate
num_target_samples = int(duration * 16000)
x_orig = np.linspace(0, duration, len(mono))
x_target = np.linspace(0, duration, num_target_samples)
resampled = np.interp(x_target, x_orig, mono)

# Convert to int16
clipped = np.clip(resampled, -1.0, 1.0)
audio_int16 = (clipped * 32767).astype(np.int16)

print(f"\nResampled shape: {audio_int16.shape}")
print(f"Resampled Min: {np.min(audio_int16)}")
print(f"Resampled Max: {np.max(audio_int16)}")
print(f"Resampled RMS: {np.sqrt(np.mean(audio_int16.astype(float)**2))}")

# Save to wav
with wave.open("test_record.wav", "wb") as wav_file:
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)
    wav_file.setframerate(16000)
    wav_file.writeframes(audio_int16.tobytes())

print("Saved to test_record.wav.")
