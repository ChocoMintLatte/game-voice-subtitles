import warnings
warnings.filterwarnings("ignore", message=".*discontinuity.*")
import soundcard as sc
import numpy as np
import queue
import wave
import io
import time
import threading

class AudioLoopbackCapture(threading.Thread):
    def __init__(self, output_queue, threshold=0.01, silence_timeout=0.5, max_speech_duration=3.0, sample_rate_target=16000, level_callback=None, device_idx=-1):
        super().__init__()
        self.output_queue = output_queue
        self.threshold = threshold
        self.silence_timeout = silence_timeout
        self.max_speech_duration = max_speech_duration
        self.sample_rate_target = sample_rate_target
        self.level_callback = level_callback
        self.device_idx = device_idx
        
        self.running = False
        self.loopback_mic = None
        self.native_sr = 48000
        self.native_channels = 2
        
        # Audio buffering
        self.audio_buffer = []
        self.is_speaking = False
        self.silence_start_time = None
        self.speech_start_time = None
        
        self.setup_device()
        
    def setup_device(self):
        try:
            speakers = sc.all_speakers()
            selected_speaker = None
            
            # Scenario A: Specific speaker index selected (device_idx >= 0)
            if self.device_idx is not None and self.device_idx >= 0 and self.device_idx < len(speakers):
                selected_speaker = speakers[self.device_idx]
                print(f"[Audio] 수동 선택 스피커: {selected_speaker.name} (Index: {self.device_idx})")
            else:
                selected_speaker = sc.default_speaker()
                print(f"[Audio] 기본 스피커 선택: {selected_speaker.name}")
                
            # Find loopback microphone associated with selected speaker
            mics = sc.all_microphones(include_loopback=True)
            for mic in mics:
                if mic.name == selected_speaker.name:
                    self.loopback_mic = mic
                    break
            
            # Fallback matching
            if not self.loopback_mic:
                for mic in mics:
                    if selected_speaker.name in mic.name or mic.name in selected_speaker.name:
                        self.loopback_mic = mic
                        break
                        
            # Final fallback
            if not self.loopback_mic:
                for mic in mics:
                    if "loopback" in mic.name.lower() or "what u hear" in mic.name.lower() or "mix" in mic.name.lower():
                        self.loopback_mic = mic
                        break
                        
            if not self.loopback_mic:
                self.loopback_mic = sc.default_microphone()
                
            print(f"[Audio] 최종 선택된 캡처 장치(루프백): {self.loopback_mic.name}")
        except Exception as e:
            raise RuntimeError(f"soundcard 장치 설정 실패: {e}")

    def resample_and_mono(self, audio_data):
        if self.native_channels > 1:
            mono_data = np.mean(audio_data, axis=1)
        else:
            mono_data = audio_data.flatten()
            
        if self.native_sr == self.sample_rate_target:
            return mono_data
            
        duration = len(mono_data) / self.native_sr
        num_target_samples = int(duration * self.sample_rate_target)
        
        x_orig = np.linspace(0, duration, len(mono_data))
        x_target = np.linspace(0, duration, num_target_samples)
        
        resampled = np.interp(x_target, x_orig, mono_data)
        return resampled

    def float32_to_int16(self, audio_data):
        clipped = np.clip(audio_data, -1.0, 1.0)
        return (clipped * 32767).astype(np.int16)

    def create_wav_bytes(self, audio_int16):
        bio = io.BytesIO()
        with wave.open(bio, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate_target)
            wav_file.writeframes(audio_int16.tobytes())
        return bio.getvalue()

    def run(self):
        self.running = True
        block_size = int(self.native_sr * 0.1) # 100ms blocks
        
        try:
            with self.loopback_mic.recorder(samplerate=self.native_sr, channels=self.native_channels) as recorder:
                print(f"[Audio] 루프백 스트림 작동 중: {self.loopback_mic.name}")
                while self.running:
                    indata = recorder.record(numframes=block_size)
                    
                    if self.native_channels > 1:
                        mono_frame = np.mean(indata, axis=1)
                    else:
                        mono_frame = indata.flatten()
                        
                    rms = np.sqrt(np.mean(mono_frame**2))
                    if self.level_callback:
                        self.level_callback(rms)
                    
                    now = time.time()
                    
                    if rms > self.threshold:
                        if not self.is_speaking:
                            print("\n[Audio] 음성 감지 시작...")
                            self.is_speaking = True
                            self.speech_start_time = now
                        self.audio_buffer.append(indata.copy())
                        self.silence_start_time = None
                        
                        # Max continuous speech check (3.0s max chunk)
                        if self.speech_start_time and (now - self.speech_start_time > self.max_speech_duration):
                            print("[Audio] 최대 발화 시간 도달. 자막 중간 처리 중...")
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
                                print("[Audio] 음성 종료 감지(0.5초 무음). 자막 처리 중...")
                                recorded_data = np.concatenate(self.audio_buffer, axis=0)
                                self.audio_buffer = []
                                self.is_speaking = False
                                self.silence_start_time = None
                                self.speech_start_time = None
                                self.process_and_push(recorded_data)
        except Exception as e:
            print(f"[Audio Error] 스트림 오류: {e}")
            self.running = False

    def process_and_push(self, raw_audio):
        try:
            resampled = self.resample_and_mono(raw_audio)
            audio_int16 = self.float32_to_int16(resampled)
            wav_bytes = self.create_wav_bytes(audio_int16)
            self.output_queue.put(wav_bytes)
        except Exception as e:
            print(f"[Audio Processing Error] {e}")

    def stop(self):
        self.running = False
        print("[Audio] 루프백 스트림 중지 요청됨.")
