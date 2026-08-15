import warnings
warnings.filterwarnings("ignore", message=".*discontinuity.*")
import soundcard as sc
import numpy as np
import collections
import queue
import wave
import io
import time
import math
from PyQt6.QtCore import QThread, pyqtSignal

try:
    from scipy.signal import resample_poly
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


class AudioLoopbackCapture(QThread):
    # Signals for thread-safe Qt communication
    level_changed = pyqtSignal(float)
    audio_captured = pyqtSignal(bytes)
    error_occurred = pyqtSignal(str)
    status_message = pyqtSignal(str)

    def __init__(
        self,
        output_queue=None,
        threshold=0.003,
        silence_timeout=0.5,
        max_speech_duration=3.0,
        sample_rate_target=16000,
        device_idx=-1,
        parent=None
    ):
        super().__init__(parent)
        self.output_queue = output_queue
        self.threshold = threshold
        self.silence_timeout = silence_timeout
        self.max_speech_duration = max_speech_duration
        self.sample_rate_target = sample_rate_target
        self.device_idx = device_idx
        
        self.running = False
        self.loopback_mic = None
        self.native_sr = 48000
        self.native_channels = 2
        
        # Audio buffering & pre-buffer (300ms ring buffer to preserve word starts)
        self.pre_buffer = collections.deque(maxlen=3)
        self.audio_buffer = []
        self.is_speaking = False
        self.silence_start_time = None
        self.speech_start_time = None
        
        self.setup_device()

    def setup_device(self):
        """Finds and binds the appropriate WASAPI loopback capture device."""
        try:
            speakers = sc.all_speakers()
            selected_speaker = None
            
            # Scenario A: Specific speaker index selected (device_idx >= 0)
            if self.device_idx is not None and 0 <= self.device_idx < len(speakers):
                selected_speaker = speakers[self.device_idx]
                print(f"[Audio] 수동 선택 스피커: {selected_speaker.name} (Index: {self.device_idx})")
            else:
                selected_speaker = sc.default_speaker()
                print(f"[Audio] 기본 스피커 선택: {selected_speaker.name}")
                
            # 1. First priority: Match by exact speaker device ID (100% reliable)
            try:
                mic_by_id = sc.get_microphone(id=selected_speaker.id, include_loopback=True)
                if mic_by_id and getattr(mic_by_id, 'isloopback', False):
                    self.loopback_mic = mic_by_id
            except Exception:
                self.loopback_mic = None

            # 2. Match by exact speaker name
            if not self.loopback_mic:
                mics = sc.all_microphones(include_loopback=True)
                for mic in mics:
                    if getattr(mic, 'isloopback', False) and mic.name == selected_speaker.name:
                        self.loopback_mic = mic
                        break
            
            # 3. Fallback matching by partial name
            if not self.loopback_mic:
                mics = sc.all_microphones(include_loopback=True)
                for mic in mics:
                    if getattr(mic, 'isloopback', False) and (selected_speaker.name in mic.name or mic.name in selected_speaker.name):
                        self.loopback_mic = mic
                        break
                        
            # 4. Fallback to any loopback device
            if not self.loopback_mic:
                mics = sc.all_microphones(include_loopback=True)
                for mic in mics:
                    if getattr(mic, 'isloopback', False):
                        self.loopback_mic = mic
                        break

            if not self.loopback_mic:
                warning_msg = "스피커 루프백(WASAPI) 장치를 찾지 못해 기본 마이크로 대체합니다."
                print(f"[Audio Warning] {warning_msg}")
                self.loopback_mic = sc.default_microphone()
                
            print(f"[Audio] 최종 선택된 캡처 장치: {self.loopback_mic.name} (Loopback: {getattr(self.loopback_mic, 'isloopback', False)})")
        except Exception as e:
            err_msg = f"오디오 캡처 장치 설정 실패: {e}"
            print(f"[Audio Error] {err_msg}")
            self.error_occurred.emit(err_msg)
            raise RuntimeError(err_msg)

    def resample_and_mono(self, audio_data: np.ndarray) -> np.ndarray:
        """
        Converts stereo/multi-channel audio to mono and resamples to target sample rate
        using high-quality polyphase anti-aliasing filtering.
        """
        # 1. Multi-channel to Mono
        if self.native_channels > 1 and audio_data.ndim > 1:
            mono_data = np.mean(audio_data, axis=1)
        else:
            mono_data = audio_data.flatten()
            
        if self.native_sr == self.sample_rate_target:
            return mono_data
            
        # 2. High-Quality Polyphase Anti-Aliasing Resampling
        if SCIPY_AVAILABLE:
            gcd = math.gcd(self.native_sr, self.sample_rate_target)
            up = self.sample_rate_target // gcd
            down = self.native_sr // gcd
            resampled = resample_poly(mono_data, up, down).astype(np.float32)
            return resampled
        else:
            # Fallback: Simple decimation if integer ratio (e.g. 48000 -> 16000)
            if self.native_sr % self.sample_rate_target == 0:
                step = self.native_sr // self.sample_rate_target
                kernel = np.ones(step) / step
                filtered = np.convolve(mono_data, kernel, mode='same')
                return filtered[::step].astype(np.float32)
            else:
                duration = len(mono_data) / self.native_sr
                num_target_samples = int(duration * self.sample_rate_target)
                x_orig = np.linspace(0, duration, len(mono_data), endpoint=False)
                x_target = np.linspace(0, duration, num_target_samples, endpoint=False)
                return np.interp(x_target, x_orig, mono_data).astype(np.float32)

    def float32_to_int16(self, audio_data: np.ndarray) -> np.ndarray:
        clipped = np.clip(audio_data, -1.0, 1.0)
        return (clipped * 32767).astype(np.int16)

    def create_wav_bytes(self, audio_int16: np.ndarray) -> bytes:
        bio = io.BytesIO()
        with wave.open(bio, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate_target)
            wav_file.writeframes(audio_int16.tobytes())
        return bio.getvalue()

    def run(self):
        self.running = True
        block_size = int(self.native_sr * 0.1)  # 100ms chunks
        
        try:
            with self.loopback_mic.recorder(samplerate=self.native_sr, channels=self.native_channels) as recorder:
                print(f"[Audio] 루프백 스트림 작동 시작: {self.loopback_mic.name} (감지 임계값: {self.threshold:.4f})")
                while self.running:
                    indata = recorder.record(numframes=block_size)
                    
                    if self.native_channels > 1 and indata.ndim > 1:
                        mono_frame = np.mean(indata, axis=1)
                    else:
                        mono_frame = indata.flatten()
                        
                    rms = float(np.sqrt(np.mean(mono_frame**2)))
                    # Emit Qt signal safely to GUI thread for volume bar
                    self.level_changed.emit(rms)
                    
                    now = time.time()
                    
                    if rms > self.threshold:
                        if not self.is_speaking:
                            print(f"\n[Audio] 음성 감지 시작 (RMS: {rms:.4f} > 임계값: {self.threshold:.4f})")
                            self.is_speaking = True
                            self.speech_start_time = now
                            # Prepend pre-buffer to preserve first word
                            self.audio_buffer.extend(list(self.pre_buffer))
                            
                        self.audio_buffer.append(indata.copy())
                        self.silence_start_time = None
                        
                        # Max continuous speech check (e.g. 3.0s max chunk)
                        if self.speech_start_time and (now - self.speech_start_time > self.max_speech_duration):
                            print("[Audio] 최대 발화 시간(3초) 도달 -> 자막 처리 중...")
                            recorded_data = np.concatenate(self.audio_buffer, axis=0)
                            self.audio_buffer = []
                            self.speech_start_time = now
                            self.process_and_push(recorded_data)
                    else:
                        if self.is_speaking:
                            self.audio_buffer.append(indata.copy())
                            if self.silence_start_time is None:
                                self.silence_start_time = now
                            elif now - self.silence_start_time > self.silence_timeout:
                                print(f"[Audio] 음성 종료 감지(0.5초 무음) -> 자막 처리 중...")
                                recorded_data = np.concatenate(self.audio_buffer, axis=0)
                                self.audio_buffer = []
                                self.is_speaking = False
                                self.silence_start_time = None
                                self.speech_start_time = None
                                self.process_and_push(recorded_data)
                        else:
                            # Keep pre-buffer fresh while silent
                            self.pre_buffer.append(indata.copy())
        except Exception as e:
            err_msg = f"루프백 오디오 스트림 오류: {e}"
            print(f"[Audio Error] {err_msg}")
            self.error_occurred.emit(err_msg)
        finally:
            self.running = False
            print("[Audio] 루프백 스트림 스레드 종료됨.")

    def process_and_push(self, raw_audio: np.ndarray):
        try:
            resampled = self.resample_and_mono(raw_audio)
            audio_int16 = self.float32_to_int16(resampled)
            wav_bytes = self.create_wav_bytes(audio_int16)
            
            # Emit Qt signal
            self.audio_captured.emit(wav_bytes)
            
            # Put into queue if configured
            if self.output_queue is not None:
                self.output_queue.put(wav_bytes)
        except Exception as e:
            print(f"[Audio Processing Error] {e}")

    def stop(self):
        self.running = False
