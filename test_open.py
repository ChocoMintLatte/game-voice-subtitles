import sounddevice as sd
import numpy as np

# Find loopback devices
devices = sd.query_devices()
host_apis = sd.query_hostapis()

loopback_keywords = ['loopback', '루프백', 'what u hear', 'stereo mix', '스테레오 믹스', 'wave out mix']

print("=== ATTEMPTING TO OPEN LOOPBACK DEVICES ===")
for idx, dev in enumerate(devices):
    name_lower = dev['name'].lower()
    if dev['max_input_channels'] > 0 and any(kw in name_lower for kw in loopback_keywords):
        api_name = host_apis[dev['hostapi']]['name']
        print(f"\nTrying Device {idx}: {dev['name']}")
        print(f"  API: {api_name}")
        print(f"  Max Channels: {dev['max_input_channels']}")
        print(f"  Default Samplerate: {dev['default_samplerate']}")
        
        # Try opening with default settings
        try:
            def callback(indata, frames, time, status):
                pass
            
            # Try native rate & channels
            samplerate = int(dev['default_samplerate'])
            channels = dev['max_input_channels']
            
            with sd.InputStream(device=idx, channels=channels, samplerate=samplerate, callback=callback):
                print("  -> SUCCESS: Opened with native rate & channels")
                continue
        except Exception as e1:
            print(f"  -> FAILED native: {e1}")
            
        # Try mono and 16000Hz
        try:
            with sd.InputStream(device=idx, channels=1, samplerate=16000, callback=callback):
                print("  -> SUCCESS: Opened with 16000Hz Mono")
                continue
        except Exception as e2:
            print(f"  -> FAILED 16000Hz Mono: {e2}")
            
        # Try default channels, 44100Hz
        try:
            with sd.InputStream(device=idx, channels=1, samplerate=44100, callback=callback):
                print("  -> SUCCESS: Opened with 44100Hz Mono")
                continue
        except Exception as e3:
            print(f"  -> FAILED 44100Hz Mono: {e3}")
