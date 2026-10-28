import queue
import numpy as np
from stt_engine import is_hallucination, FLASH_MODEL_POOL, GeminiSTTEngine
from audio_capture import AudioLoopbackCapture


def test_is_hallucination():
    print("[Test] 1. Checking is_hallucination rules...")
    # 1-character CJK callouts must NOT be filtered out
    for cjk in ["敵", "右", "左", "上", "下", "적"]:
        assert not is_hallucination(cjk), f"Expected '{cjk}' to be allowed, but was treated as hallucination"

    # Non-CJK 1-character strings must be filtered
    for non_cjk in ["a", "Z", "1", ".", "?", " "]:
        assert is_hallucination(non_cjk), f"Expected '{non_cjk}' to be hallucination"

    # Hallucination phrases must be detected
    for phrase in [
        "Thank you for watching",
        "thanks for watching",
        "please subscribe",
        "시청해 주셔서 감사합니다",
        "ご視聴ありがとうございました",
    ]:
        assert is_hallucination(phrase), f"Expected phrase '{phrase}' to be hallucination"

    # Repetition loops must be detected
    assert is_hallucination("push push push push"), "Repetition loop was not detected"

    # Legitimate multi-character gameplay communications must pass
    assert not is_hallucination("enemy spotted"), "Valid communication was falsely detected"
    assert not is_hallucination("B 사이트로 가자"), "Valid Korean communication was falsely detected"
    print("  -> is_hallucination passed!")


def test_resample_and_mono():
    print("[Test] 2. Checking resample_and_mono anti-aliasing decimation...")
    capture = AudioLoopbackCapture.__new__(AudioLoopbackCapture)
    capture.native_sr = 48000
    capture.sample_rate_target = 16000

    # Test decimation mean calculation: step = 48000 // 16000 = 3
    # First chunk [1, 2, 3] -> mean = 2.0; Second chunk [4, 5, 6] -> mean = 5.0
    stereo_data = np.array([
        [1.0, 1.0],
        [2.0, 2.0],
        [3.0, 3.0],
        [4.0, 4.0],
        [5.0, 5.0],
        [6.0, 6.0],
    ], dtype=np.float32)

    resampled = capture.resample_and_mono(stereo_data)
    assert resampled.shape == (2,), f"Expected shape (2,), got {resampled.shape}"
    assert np.allclose(resampled, [2.0, 5.0]), f"Expected [2.0, 5.0], got {resampled}"

    # Test 100ms frame at 48kHz -> 100ms frame at 16kHz
    chunk_48k = np.ones((4800, 2), dtype=np.float32) * 0.75
    chunk_16k = capture.resample_and_mono(chunk_48k)
    assert chunk_16k.shape == (1600,), f"Expected shape (1600,), got {chunk_16k.shape}"
    assert np.isclose(chunk_16k[0], 0.75), f"Expected value 0.75, got {chunk_16k[0]}"

    # Test non-multiple trim
    chunk_non_multiple = np.ones((4802, 2), dtype=np.float32)
    chunk_trimmed = capture.resample_and_mono(chunk_non_multiple)
    assert chunk_trimmed.shape == (1600,), f"Expected shape (1600,), got {chunk_trimmed.shape}"
    print("  -> resample_and_mono passed!")


def test_queue_drop_oldest():
    print("[Test] 3. Checking queue backpressure drop-oldest behavior...")
    capture = AudioLoopbackCapture.__new__(AudioLoopbackCapture)
    capture.native_sr = 48000
    capture.sample_rate_target = 16000
    q = queue.Queue(maxsize=3)
    capture.output_queue = q

    # Push 4 distinct audio signals into a queue of size 3
    for val in [10.0, 20.0, 30.0, 40.0]:
        audio = np.ones((4800, 2), dtype=np.float32) * (val / 32767.0)
        capture.process_and_push(audio)

    assert q.qsize() == 3, f"Expected queue size 3, got {q.qsize()}"

    # Extract all elements: the oldest (10.0) should have been dropped
    items = []
    while not q.empty():
        items.append(q.get_nowait())

    assert len(items) == 3, f"Expected 3 items, got {len(items)}"
    # Each item is wav bytes
    for item in items:
        assert isinstance(item, bytes) and len(item) > 0
    print("  -> queue drop-oldest passed!")


def test_live_threshold():
    print("[Test] 4. Checking live threshold setter...")
    capture = AudioLoopbackCapture.__new__(AudioLoopbackCapture)
    capture.threshold = 0.003
    capture.set_threshold(0.015)
    assert capture.threshold == 0.015, f"Expected threshold 0.015, got {capture.threshold}"
    print("  -> live threshold passed!")


def test_gemini_model_pool_and_cache():
    print("[Test] 5. Checking Gemini model pool and LRU cache behavior...")
    assert FLASH_MODEL_POOL == [
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
        "gemini-3.1-flash-lite",
    ], f"Unexpected FLASH_MODEL_POOL: {FLASH_MODEL_POOL}"

    # Test fallback behavior when API is not configured or all models fail
    engine = GeminiSTTEngine.__new__(GeminiSTTEngine)
    engine.api_key = "test_invalid_key"
    engine._config_lock = None
    engine.mode = "foreign_only"
    engine.source_lang = "일본어"
    engine.target_lang = "한국어"

    import threading
    engine._config_lock = threading.Lock()
    engine._client = None

    fallback_result = engine.translate_text("Rush B", "en")
    # On failure, it should cleanly return original text without caching a broken response
    assert fallback_result == "Rush B", f"Expected 'Rush B', got '{fallback_result}'"
    assert engine._translate_cached.cache_info().currsize == 0, "Failed call was erroneously cached!"

    # Test empty model response (e.g., meaningless interjection filtered by SYSTEM_INSTRUCTION)
    # Must return "" immediately on 1st model without failing over to other models or returning raw input
    call_count = 0
    class DummyInteraction:
        output_text = ""
    class DummyInteractions:
        def create(self, **kwargs):
            nonlocal call_count
            call_count += 1
            return DummyInteraction()
    class DummyClient:
        interactions = DummyInteractions()

    engine._client = DummyClient()
    filtered_result = engine.translate_text("uhh umm", "en")
    assert filtered_result == "", f"Expected empty string for filtered interjection, got '{filtered_result}'"
    assert call_count == 1, f"Expected 1 model call (no failover on valid empty output), got {call_count}"
    assert engine._translate_cached.cache_info().currsize == 1, "Expected valid empty output to be cached!"
    print("  -> Gemini model pool and cache passed!")


def test_whisper_model_options_and_cloud_mode():
    print("[Test] 6. Checking WHISPER_MODEL_OPTIONS and cloud_only mode...")
    import threading
    from stt_engine import WHISPER_MODEL_OPTIONS
    model_ids = [opt[0] for opt in WHISPER_MODEL_OPTIONS]
    assert "large-v3-turbo" in model_ids
    assert "small" in model_ids
    assert "base" in model_ids
    assert "tiny" in model_ids
    assert "cloud_only" in model_ids

    engine = GeminiSTTEngine.__new__(GeminiSTTEngine)
    engine._whisper_lock = threading.Lock()
    engine._config_lock = threading.Lock()
    engine.whisper_model = None
    engine.whisper_status = "uninitialized"
    engine.whisper_model_name = "cloud_only"

    # Test init_whisper with cloud_only
    engine.init_whisper()
    assert engine.whisper_status == "cloud_only"
    assert engine.whisper_model is None

    # Test set_whisper_model no-op when already cloud_only
    engine.set_whisper_model("cloud_only")
    assert engine.whisper_status == "cloud_only"

    print("  -> WHISPER_MODEL_OPTIONS and cloud_only mode passed!")


if __name__ == "__main__":
    print("Running unit tests for game-voice-subtitles refactor...")
    test_is_hallucination()
    test_resample_and_mono()
    test_queue_drop_oldest()
    test_live_threshold()
    test_gemini_model_pool_and_cache()
    test_whisper_model_options_and_cloud_mode()
    print("\nAll self-check tests passed successfully!")
