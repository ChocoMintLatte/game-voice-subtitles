import os
import sys
import sounddevice as sd
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, 
    QPushButton, QComboBox, QSlider, QProgressBar, QFormLayout,
    QGraphicsOpacityEffect, QApplication
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QColor

class SubtitleOverlay(QWidget):
    # Signal to update text safely from other threads
    text_updated = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        
    def init_ui(self):
        # Frameless, Always on Top, Click-through window
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowTransparentForInput |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setLayout(layout)
        
        # Subtitle Label
        self.label = QLabel("")
        self.label.setFont(QFont("Malgun Gothic", 24, QFont.Weight.Bold))
        self.label.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                background-color: rgba(15, 15, 15, 0.75);
                border: 1.5px solid rgba(255, 255, 255, 0.15);
                border-radius: 12px;
                padding: 12px 28px;
            }
        """)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        
        # Hide label initially
        self.label.hide()
        
        # Geometry: Center-bottom of primary screen
        screen = QApplication.primaryScreen().geometry()
        width = int(screen.width() * 0.6)
        height = 150
        x = int((screen.width() - width) / 2)
        y = int(screen.height() - height - 120)  # 120px from bottom
        self.setGeometry(x, y, width, height)
        
        # Fade In/Out Opacity setup
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)
        
        # Animation config
        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        # Silence/hide timer
        self.fade_timer = QTimer(self)
        self.fade_timer.setSingleShot(True)
        self.fade_timer.timeout.connect(self.fade_out)
        
        self.text_updated.connect(self.update_subtitle)
        
    @pyqtSlot(str)
    def update_subtitle(self, text):
        if not text.strip():
            return
            
        self.label.setText(text)
        self.label.show()
        
        # Reset timers/animations
        self.fade_timer.stop()
        self.animation.stop()
        
        # Quick fade in if not visible
        if self.opacity_effect.opacity() < 1.0:
            self.opacity_effect.setOpacity(1.0)
            self.show()
            
        # Start display timer (5 seconds)
        self.fade_timer.start(5000)
        
    def fade_out(self):
        self.animation.stop()
        self.animation.setStartValue(self.opacity_effect.opacity())
        self.animation.setEndValue(0.0)
        
        try:
            self.animation.finished.disconnect()
        except TypeError:
            pass
            
        self.animation.finished.connect(self.on_fade_finished)
        self.animation.start()
        
    def on_fade_finished(self):
        if self.opacity_effect.opacity() == 0.0:
            self.label.hide()
            self.hide()

    @pyqtSlot(int)
    def change_font_size(self, size):
        self.label.setFont(QFont("Malgun Gothic", size, QFont.Weight.Bold))


class ControlPanel(QWidget):
    # Signals to communicate with the main thread / capture system
    start_requested = pyqtSignal(int, float) # (device_idx, threshold)
    stop_requested = pyqtSignal()
    api_key_saved = pyqtSignal(str)
    font_size_changed = pyqtSignal(int)
    
    def __init__(self, stt_engine):
        super().__init__()
        self.stt_engine = stt_engine
        self.is_running = False
        self.init_ui()
        self.load_settings()
        
    def init_ui(self):
        self.setWindowTitle("게임 보이스 자막 오버레이 - 컨트롤 패널")
        self.resize(480, 560)
        self.setStyleSheet("""
            QWidget {
                background-color: #1A1A24;
                color: #E2E8F0;
                font-family: 'Malgun Gothic';
            }
            QLabel {
                font-size: 10pt;
                font-weight: bold;
                color: #CBD5E1;
            }
            QLineEdit {
                background-color: #0F172A;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 8px;
                color: #F8FAFC;
                font-size: 10pt;
            }
            QLineEdit:focus {
                border-color: #3B82F6;
            }
            QComboBox {
                background-color: #0F172A;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 8px;
                color: #F8FAFC;
                font-size: 10pt;
            }
            QPushButton {
                background-color: #2563EB;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px;
                font-weight: bold;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #3B82F6;
            }
            QPushButton:pressed {
                background-color: #1D4ED8;
            }
            QPushButton#btn_toggle {
                background-color: #10B981;
            }
            QPushButton#btn_toggle:hover {
                background-color: #34D399;
            }
            QPushButton#btn_toggle[running="true"] {
                background-color: #EF4444;
            }
            QPushButton#btn_toggle[running="true"]:hover {
                background-color: #F87171;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #334155;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #3B82F6;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QProgressBar {
                background-color: #0F172A;
                border: 1px solid #334155;
                border-radius: 4px;
                text-align: center;
                height: 12px;
            }
            QProgressBar::chunk {
                background-color: #10B981;
                border-radius: 3px;
            }
        """)
        
        main_layout = QVBoxLayout()
        main_layout.setSpacing(18)
        main_layout.setContentsMargins(24, 24, 24, 24)
        self.setLayout(main_layout)
        
        # Title
        title_label = QLabel("게임 보이스 자막 오버레이")
        title_label.setFont(QFont("Malgun Gothic", 18, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #3B82F6; margin-bottom: 5px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)
        
        # Form Layout
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        
        # 1. Gemini API Key Input
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Google AI Studio API Key를 입력하세요")
        
        api_layout = QHBoxLayout()
        api_layout.addWidget(self.api_key_input)
        
        self.btn_show_key = QPushButton("보기")
        self.btn_show_key.setFixedWidth(60)
        self.btn_show_key.setStyleSheet("background-color: #475569; padding: 7px;")
        self.btn_show_key.clicked.connect(self.toggle_key_visibility)
        api_layout.addWidget(self.btn_show_key)
        
        self.btn_save_key = QPushButton("저장")
        self.btn_save_key.setFixedWidth(60)
        self.btn_save_key.setStyleSheet("background-color: #334155; padding: 7px;")
        self.btn_save_key.clicked.connect(self.save_api_key)
        api_layout.addWidget(self.btn_save_key)
        
        form_layout.addRow("Gemini API Key:", api_layout)
        
        # 2. Audio Device Selection
        self.device_combo = QComboBox()
        self.refresh_devices()
        form_layout.addRow("오디오 장치 (출력):", self.device_combo)
        
        # 2.5 Translation Mode & Language Selection
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("외국어만 번역 (한국어 음성 무시)", "foreign_only")
        self.mode_combo.addItem("지정한 외국어만 번역", "specific")
        self.mode_combo.addItem("모든 음성 자막 (한국어 받아쓰기 + 외국어 번역)", "all")
        self.mode_combo.currentIndexChanged.connect(self.update_translation_config)
        form_layout.addRow("번역 동작 모드:", self.mode_combo)

        self.source_lang_combo = QComboBox()
        for lang in ["일본어", "중국어", "영어", "스페인어", "독일어", "프랑스어", "러시아어"]:
            self.source_lang_combo.addItem(lang, lang)
        self.source_lang_combo.currentIndexChanged.connect(self.update_translation_config)
        form_layout.addRow("지정 번역 대상 언어:", self.source_lang_combo)

        # 3. Sensitivity Threshold
        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setMinimum(1)
        self.threshold_slider.setMaximum(100)
        self.threshold_slider.setValue(10) # Default 10/1000 = 0.01
        self.threshold_slider.valueChanged.connect(self.update_threshold_label)
        
        self.threshold_label = QLabel("0.010 (민감도)")
        self.threshold_label.setStyleSheet("font-weight: normal; color: #94A3B8;")
        
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(self.threshold_slider)
        threshold_layout.addWidget(self.threshold_label)
        
        form_layout.addRow("음성 감지 데시벨:", threshold_layout)

        # 3.5 Font Size Slider
        self.font_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_size_slider.setMinimum(16)
        self.font_size_slider.setMaximum(48)
        self.font_size_slider.setValue(24)
        self.font_size_slider.valueChanged.connect(self.update_font_size_label)
        
        self.font_size_label = QLabel("24pt")
        self.font_size_label.setStyleSheet("font-weight: normal; color: #94A3B8;")
        
        font_layout = QHBoxLayout()
        font_layout.addWidget(self.font_size_slider)
        font_layout.addWidget(self.font_size_label)
        
        form_layout.addRow("자막 글꼴 크기:", font_layout)
        
        # 4. Audio Input Level meter (Real-time)
        self.level_bar = QProgressBar()
        self.level_bar.setMinimum(0)
        self.level_bar.setMaximum(100)
        self.level_bar.setValue(0)
        self.level_bar.setTextVisible(False)
        form_layout.addRow("스피커 출력 레벨:", self.level_bar)
        
        main_layout.addLayout(form_layout)

        # 4.5 Subtitle Size Preview Label
        self.preview_label = QLabel("자막이 이 크기로 표시됩니다.")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                background-color: rgba(15, 15, 15, 0.75);
                border: 1.5px solid rgba(255, 255, 255, 0.15);
                border-radius: 12px;
                padding: 12px;
                min-height: 50px;
            }
        """)
        self.preview_label.setFont(QFont("Malgun Gothic", 24, QFont.Weight.Bold))
        main_layout.addWidget(self.preview_label)
        
        # Status text
        self.status_label = QLabel("상태: 정지됨")
        self.status_label.setStyleSheet("color: #94A3B8; font-weight: normal; margin-top: 5px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.status_label)
        
        # Toggle Button
        self.btn_toggle = QPushButton("시작")
        self.btn_toggle.setObjectName("btn_toggle")
        self.btn_toggle.setProperty("running", "false")
        self.btn_toggle.clicked.connect(self.toggle_running)
        main_layout.addWidget(self.btn_toggle)
        
        # Level meter timer
        self.level_timer = QTimer(self)
        self.level_timer.timeout.connect(self.poll_level)
        self.current_level = 0
        
    def toggle_key_visibility(self):
        if self.api_key_input.echoMode() == QLineEdit.EchoMode.Password:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_show_key.setText("숨기기")
        else:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_show_key.setText("보기")
            
    def refresh_devices(self):
        self.device_combo.clear()
        try:
            import soundcard as sc
            speakers = sc.all_speakers()
            self.device_combo.addItem("기본 오디오 장치 (루프백 자동 검색)", -1)
            for idx, sp in enumerate(speakers):
                self.device_combo.addItem(sp.name, idx)
        except Exception as e:
            self.device_combo.addItem(f"장치 검색 오류: {e}", -1)
            
    def update_threshold_label(self):
        val = self.threshold_slider.value() / 1000.0
        self.threshold_label.setText(f"{val:.3f}")
        
    def get_threshold(self):
        return self.threshold_slider.value() / 1000.0

    def update_translation_config(self):
        mode = self.mode_combo.currentData() or "foreign_only"
        source_lang = self.source_lang_combo.currentData() or "영어"
        
        # Show/hide source lang combo depending on mode
        self.source_lang_combo.setEnabled(mode == "specific")
        
        # Update STT Engine
        self.stt_engine.set_translation_config(mode=mode, source_lang=source_lang, target_lang="한국어")
        
        # Save to .env
        self.save_env_var("TRANSLATION_MODE", mode)
        self.save_env_var("SOURCE_LANG", source_lang)

    def save_env_var(self, key, val):
        env_path = ".env"
        lines = []
        found = False
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for i, line in enumerate(lines):
                if line.strip().startswith(f"{key}="):
                    lines[i] = f"{key}={val}\n"
                    found = True
                    break
        if not found:
            lines.append(f"{key}={val}\n")
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

    def update_font_size_label(self):
        val = self.font_size_slider.value()
        self.font_size_label.setText(f"{val}pt")
        self.font_size_changed.emit(val)
        
        # Update preview label font size
        if hasattr(self, 'preview_label'):
            self.preview_label.setFont(QFont("Malgun Gothic", val, QFont.Weight.Bold))
        
        self.save_env_var("FONT_SIZE", val)

    @pyqtSlot(str)
    def update_recognized_text(self, text):
        if text.strip() and not text.startswith("[에러:"):
            self.preview_label.setText(text)
        
    def save_api_key(self):
        key = self.api_key_input.text().strip()
        if not key:
            self.status_label.setText("에러: 빈 API Key는 저장할 수 없습니다.")
            return
            
        self.save_env_var("GEMINI_API_KEY", key)
        self.stt_engine.set_api_key(key)
        self.status_label.setText("상태: API Key 저장 완료.")
        
    def load_settings(self):
        # Load from .env if exists
        if os.path.exists(".env"):
            with open(".env", "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("GEMINI_API_KEY="):
                        key = line.strip().split("GEMINI_API_KEY=")[1]
                        self.api_key_input.setText(key)
                        self.stt_engine.set_api_key(key)
                    elif line.strip().startswith("FONT_SIZE="):
                        try:
                            val = int(line.strip().split("FONT_SIZE=")[1])
                            self.font_size_slider.setValue(val)
                            self.font_size_label.setText(f"{val}pt")
                        except Exception:
                            pass
                    elif line.strip().startswith("TRANSLATION_MODE="):
                        mode = line.strip().split("TRANSLATION_MODE=")[1]
                        idx = self.mode_combo.findData(mode)
                        if idx >= 0:
                            self.mode_combo.setCurrentIndex(idx)
                    elif line.strip().startswith("SOURCE_LANG="):
                        lang = line.strip().split("SOURCE_LANG=")[1]
                        idx = self.source_lang_combo.findData(lang)
                        if idx >= 0:
                            self.source_lang_combo.setCurrentIndex(idx)
        self.update_translation_config()
                        
    def toggle_running(self):
        if not self.is_running:
            # Starting
            key = self.api_key_input.text().strip()
            if not key:
                self.status_label.setText("에러: API Key를 먼저 저장하거나 입력하세요.")
                return
                
            self.is_running = True
            self.btn_toggle.setText("중지")
            self.btn_toggle.setProperty("running", "true")
            self.btn_toggle.style().polish(self.btn_toggle) # Force style update
            self.status_label.setText("상태: 오디오 캡처 작동 중...")
            
            # Start signals
            device_idx = self.device_combo.currentData()
            if device_idx is None:
                device_idx = -1
            threshold = self.get_threshold()
            self.start_requested.emit(device_idx, threshold)
            
            # Start level meter
            self.level_timer.start(50) # 20fps
        else:
            # Stopping
            self.is_running = False
            self.btn_toggle.setText("시작")
            self.btn_toggle.setProperty("running", "false")
            self.btn_toggle.style().polish(self.btn_toggle)
            self.status_label.setText("상태: 정지됨")
            self.level_bar.setValue(0)
            
            # Stop signals
            self.stop_requested.emit()
            self.level_timer.stop()
            
    def update_audio_level(self, rms_val):
        # Scale rms value to progress bar range (0-100)
        # RMS is usually in [0, 1.0]. A typical speech max RMS is around 0.1 ~ 0.2.
        # Let's multiply by 500 to scale it.
        scaled = int(rms_val * 500)
        self.current_level = min(max(scaled, 0), 100)
        
    def poll_level(self):
        self.level_bar.setValue(int(self.current_level))
        # Smoothly decay the meter level
        self.current_level = max(0, int(self.current_level) - 10)
        
    def closeEvent(self, event):
        # Stop background processing when control panel closes
        self.stop_requested.emit()
        event.accept()
