import sys
import queue
import os
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QIcon

# Lazy import helpers after QApplication setup to avoid COM MTA/STA mode conflict
def _load_components():
    from overlay_gui import ControlPanel, SubtitleOverlay
    from stt_engine import GeminiSTTEngine
    from audio_capture import AudioLoopbackCapture
    return ControlPanel, SubtitleOverlay, GeminiSTTEngine, AudioLoopbackCapture


def get_resource_path(relative_path: str) -> Path:
    """Returns absolute path to resource, works for dev and PyInstaller bundle."""
    if hasattr(sys, '_MEIPASS'):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parent
    return base_path / relative_path


class STTWorker(QThread):
    # Signals for thread-safe event publishing
    text_translated = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    status_message = pyqtSignal(str)

    def __init__(self, audio_queue: queue.Queue, stt_engine: GeminiSTTEngine, parent=None):
        super().__init__(parent)
        self.audio_queue = audio_queue
        self.stt_engine = stt_engine
        self.running = True
        
    def run(self):
        print("[STTWorker] 음성 변환 워커 스레드 시작됨.")
        while self.running:
            try:
                wav_bytes = self.audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue
                
            try:
                text = self.stt_engine.transcribe(wav_bytes)
                if text and text.strip():
                    print(f"[STTWorker] 변환 완료: '{text}'")
                    self.text_translated.emit(text)
            except Exception as e:
                err_msg = f"STT 변환 예외 발생: {e}"
                print(f"[STTWorker Error] {err_msg}")
                self.error_occurred.emit(err_msg)
                
        print("[STTWorker] 음성 변환 워커 스레드 정상 종료됨.")
                
    def stop(self):
        self.running = False


class AppController(QObject):
    """
    Central mediator managing application lifecycle, thread coordination,
    and safe signal/slot routing.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Load components after Qt Application COM STA is established
        ControlPanel, SubtitleOverlay, GeminiSTTEngine, AudioLoopbackCapture = _load_components()
        self.AudioLoopbackCaptureClass = AudioLoopbackCapture
        
        # 1. Initialize STT Engine
        self.stt_engine = GeminiSTTEngine()
        
        # 2. Audio Buffer Queue
        self.audio_queue = queue.Queue()
        
        # 3. Initialize Windows
        self.overlay = SubtitleOverlay()
        self.control_panel = ControlPanel(self.stt_engine)
        
        # 4. Connect GUI Signals
        self.control_panel.start_requested.connect(self.start_capture)
        self.control_panel.stop_requested.connect(self.stop_capture)
        self.control_panel.font_size_changed.connect(self.overlay.change_font_size)
        
        # Thread references
        self.capture_thread = None
        self.worker_thread = None
        
        # Set initial font size
        initial_font_size = self.control_panel.font_size_slider.value()
        self.overlay.change_font_size(initial_font_size)
        
        # Show Windows
        self.control_panel.show()
        self.overlay.show()
        
    @pyqtSlot(int, float)
    def start_capture(self, device_idx: int, threshold: float):
        print(f"[Controller] 캡처 시작 요청 (장치 ID: {device_idx}, 임계값: {threshold:.3f})")
        
        # 1. Start STT Worker Thread if not alive
        if self.worker_thread is None or not self.worker_thread.isRunning():
            self.worker_thread = STTWorker(
                audio_queue=self.audio_queue,
                stt_engine=self.stt_engine
            )
            # Route signals safely via Controller
            self.worker_thread.text_translated.connect(self.overlay.update_subtitle)
            self.worker_thread.error_occurred.connect(self.control_panel.show_error)
            self.worker_thread.start()
            
        # 2. Start Audio Loopback Capture Thread if not alive
        if self.capture_thread is None or not self.capture_thread.isRunning():
            # Flush queue
            while not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    break
                    
            self.capture_thread = self.AudioLoopbackCaptureClass(
                output_queue=self.audio_queue,
                threshold=threshold,
                silence_timeout=0.5,
                device_idx=device_idx
            )
            # Connect capture signals to GUI slots
            self.capture_thread.level_changed.connect(self.control_panel.update_audio_level)
            self.capture_thread.error_occurred.connect(self.control_panel.show_error)
            self.capture_thread.start()
            
    @pyqtSlot()
    def stop_capture(self):
        print("[Controller] 캡처 중지 요청.")
        
        if self.capture_thread and self.capture_thread.isRunning():
            self.capture_thread.stop()
            self.capture_thread.wait(1000)
            self.capture_thread = None
            
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.stop()
            self.worker_thread.wait(1000)
            self.worker_thread = None


def main():
    app = QApplication(sys.argv)
    
    # Set App Icon safely
    icon_path = get_resource_path("app_icon.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    
    # Initialize Application Controller
    controller = AppController()
    
    # Ensure background threads are safely terminated upon quitting
    app.aboutToQuit.connect(controller.stop_capture)
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
