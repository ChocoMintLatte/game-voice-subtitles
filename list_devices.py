import sounddevice as sd

print("=== HOST APIs ===")
host_apis = sd.query_hostapis()
for idx, api in enumerate(host_apis):
    print(f"API {idx}: {api['name']}")

print("\n=== ALL DEVICES ===")
devices = sd.query_devices()
for idx, dev in enumerate(devices):
    print(f"Device {idx}: {dev['name']}")
    print(f"  Host API: {host_apis[dev['hostapi']]['name']}")
    print(f"  Max Input Channels: {dev['max_input_channels']}")
    print(f"  Max Output Channels: {dev['max_output_channels']}")
    print(f"  Default Samplerate: {dev['default_samplerate']}")
    print("-" * 30)

print("\n=== DEFAULT DEVICES ===")
try:
    print(f"Default Input: {sd.query_devices(kind='input')['name']}")
except Exception as e:
    print(f"Default Input Error: {e}")
try:
    print(f"Default Output: {sd.query_devices(kind='output')['name']}")
except Exception as e:
    print(f"Default Output Error: {e}")
