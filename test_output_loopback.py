import sounddevice as sd
import time

devices = sd.query_devices()
host_apis = sd.query_hostapis()
wasapi_idx = -1
for idx, api in enumerate(host_apis):
    if api['name'] == 'Windows WASAPI':
        wasapi_idx = idx
        break

print(f"Windows WASAPI Host API Index: {wasapi_idx}")

# Find WASAPI output devices (input channels == 0, output channels > 0)
wasapi_outputs = []
for idx, dev in enumerate(devices):
    if dev['hostapi'] == wasapi_idx and dev['max_input_channels'] == 0 and dev['max_output_channels'] > 0:
        wasapi_outputs.append((idx, dev))

print("\n=== ATTEMPTING TO OPEN WASAPI OUTPUT DEVICES AS LOOPBACK INPUTS ===")
for idx, dev in wasapi_outputs:
    print(f"\nTrying Output Device {idx} as Loopback Input: {dev['name']}")
    print(f"  Channels: {dev['max_output_channels']}")
    print(f"  Samplerate: {dev['default_samplerate']}")
    
    try:
        def callback(indata, frames, time_info, status):
            pass
        
        # In sounddevice, opening an output device as input will trigger WASAPI loopback
        # if the device is an output device.
        # Note: we must specify channels equal to the output channels (usually 2).
        samplerate = int(dev['default_samplerate'])
        channels = dev['max_output_channels']
        
        with sd.InputStream(device=idx, channels=channels, samplerate=samplerate, callback=callback):
            print("  -> SUCCESS! Loopback opened successfully.")
    except Exception as e:
        print(f"  -> FAILED: {e}")
