import time

try:
    from faster_whisper import WhisperModel
    print("[faster-whisper Import]: Success!")
    
    # Try CUDA FP16 first
    try:
        print("Testing faster-whisper model loading: 'large-v3-turbo' on cuda (float16)...")
        start_time = time.time()
        model = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16")
        elapsed = time.time() - start_time
        print(f"[WhisperModel CUDA Load Success]: Took {elapsed:.2f} seconds.")
    except Exception as e:
        print(f"[WhisperModel CUDA Load Warning]: {e}")
        print("Fallback to CPU (int8)...")
        start_time = time.time()
        model = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
        elapsed = time.time() - start_time
        print(f"[WhisperModel CPU Load Success]: Took {elapsed:.2f} seconds.")
except Exception as e:
    print(f"[WhisperModel Import/Load Error]: {e}")
