import sys
import queue
import threading
from PyQt6.QtWidgets import QApplication
from overlay_gui import ControlPanel, SubtitleOverlay
from stt_engine import GeminiSTTEngine
from audio_capture import AudioLoopbackCapture

class STTWorker(threading.Thread):
    def __init__(self, audio_queue, stt_engine, text_signal):
        super().__init__(daemon=True)
        self.audio_queue = audio_queue
        self.stt_engine = stt_engine
        self.text_signal = text_signal
        self.running = True
        
    def run(self):
        print("[Worker] STT 변환 워커 스레드 시작됨.")
        while self.running:
            try:
                wav_bytes = self.audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue
                
            try:
                text = self.stt_engine.transcribe(wav_bytes)
                if text:
                    print(f"[Worker] 변환 완료: '{text}'")
                    self.text_signal.emit(text)
            except Exception as e:
                print(f"[Worker Error] 변환 중 예외 발생: {e}")
                
        print("[Worker] STT 변환 워커 스레드 종료됨.")
                
    def stop(self):
        self.running = False


class AppController:
    def __init__(self):
        # STT Engine
        self.stt_engine = GeminiSTTEngine()
        
        # Audio Queue
        self.audio_queue = queue.Queue()
        
        # Windows
        self.overlay = SubtitleOverlay()
        self.control_panel = ControlPanel(self.stt_engine)
        
        # Connect signals
        self.control_panel.start_requested.connect(self.start_capture)
        self.control_panel.stop_requested.connect(self.stop_capture)
        self.control_panel.font_size_changed.connect(self.overlay.change_font_size)
        self.overlay.text_updated.connect(self.control_panel.update_recognized_text)
        
        self.capture_thread = None
        self.worker_thread = None
        
        # Set initial font size
        initial_font_size = self.control_panel.font_size_slider.value()
        self.overlay.change_font_size(initial_font_size)
        
        # Show control panel
        self.control_panel.show()
        self.overlay.show()
        
    def start_capture(self, device_idx, threshold):
        print(f"[Controller] 캡처 시작 요청됨 (장치 인덱스: {device_idx}, 임계값: {threshold})")
        
        # 1. Start STT Worker Thread
        if self.worker_thread is None or not self.worker_thread.is_alive():
            self.worker_thread = STTWorker(
                audio_queue=self.audio_queue,
                stt_engine=self.stt_engine,
                text_signal=self.overlay.text_updated
            )
            self.worker_thread.start()
            
        # 2. Start Audio Loopback Capture Thread
        if self.capture_thread is None or not self.capture_thread.is_alive():
            # Clear remaining items in queue
            while not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    break
                    
            self.capture_thread = AudioLoopbackCapture(
                output_queue=self.audio_queue,
                threshold=threshold,
                silence_timeout=0.5,
                level_callback=self.control_panel.update_audio_level,
                device_idx=device_idx
            )
            self.capture_thread.daemon = True
            self.capture_thread.start()
            
    def stop_capture(self):
        print("[Controller] 캡처 중지 요청됨.")
        
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.stop()
            self.capture_thread.join(timeout=0.5)
            self.capture_thread = None
            
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.stop()
            self.worker_thread.join(timeout=0.5)
            self.worker_thread = None


def main():
    app = QApplication(sys.argv)
    
    # Set app icon
    from PyQt6.QtGui import QIcon
    import os
    if hasattr(sys, '_MEIPASS'):
        icon_path = os.path.join(sys._MEIPASS, "app_icon.png")
    else:
        icon_path = "app_icon.png"
        if not os.path.exists(icon_path):
            icon_path = r"C:\Users\USER\.gemini\antigravity\scratch\game-voice-subtitles\app_icon.png"
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    # Initialize controller
    controller = AppController()
    
    # Stop threads on quit
    app.aboutToQuit.connect(controller.stop_capture)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
