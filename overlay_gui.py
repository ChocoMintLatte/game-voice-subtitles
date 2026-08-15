import os
import sys
from dotenv import load_dotenv, set_key, find_dotenv
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, 
    QPushButton, QComboBox, QSlider, QProgressBar, QFormLayout,
    QGraphicsOpacityEffect, QApplication, QFrame
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QColor


class SubtitleOverlay(QWidget):
    """
    Google-styled transparent, click-through, always-on-top subtitle overlay for games.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        # Frameless, Always on Top, Click-through (Transparent for Input)
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
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        
        # Google TV / YouTube Subtitle Style Label
        self.label = QLabel("")
        self.label.setFont(QFont("Google Sans", 24, QFont.Weight.DemiBold))
        self.label.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                background-color: rgba(19, 19, 20, 0.88);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 16px;
                padding: 14px 32px;
                line-height: 1.4;
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
        
        # Animation config (Material Easing)
        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.animation.setDuration(250)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        
        # Silence/hide timer
        self.fade_timer = QTimer(self)
        self.fade_timer.setSingleShot(True)
        self.fade_timer.timeout.connect(self.fade_out)
        
    @pyqtSlot(str)
    def update_subtitle(self, text: str):
        """Displays subtitle with smooth fade in and resets the auto-hide timer."""
        if not text or not text.strip():
            return
            
        self.label.setText(text)
        self.label.show()
        
        # Reset timers/animations
        self.fade_timer.stop()
        self.animation.stop()
        
        # Quick fade in if not fully visible
        if self.opacity_effect.opacity() < 1.0:
            self.opacity_effect.setOpacity(1.0)
            self.show()
            
        # Display duration: 5 seconds
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
    def change_font_size(self, size: int):
        self.label.setFont(QFont("Google Sans", size, QFont.Weight.DemiBold))


def get_env_path() -> str:
    """Returns reliable path to .env file whether running in dev or frozen .exe."""
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, ".env")


class ControlPanel(QWidget):
    # Signals for inter-thread communication
    start_requested = pyqtSignal(int, float)  # (device_idx, threshold)
    stop_requested = pyqtSignal()
    font_size_changed = pyqtSignal(int)
    
    def __init__(self, stt_engine, parent=None):
        super().__init__(parent)
        self.stt_engine = stt_engine
        self.is_running = False
        self.env_path = get_env_path()
        self.init_ui()
        self.load_settings()
        
    def init_ui(self):
        self.setWindowTitle("Google AI 게임 보이스 자막 - 컨트롤 패널")
        self.resize(500, 520)
        
        # Google Material 3 Dark Theme Stylesheet
        self.setStyleSheet("""
            QWidget {
                background-color: #131314;
                color: #E3E3E3;
                font-family: 'Google Sans', 'Malgun Gothic', sans-serif;
            }
            QFrame#card_container {
                background-color: #1E1F20;
                border: 1px solid #333538;
                border-radius: 16px;
                padding: 16px;
            }
            QLabel {
                background-color: transparent;
                font-size: 10pt;
                color: #C4C7C5;
                font-weight: 500;
            }
            QLabel#header_title {
                background-color: transparent;
                font-size: 16pt;
                font-weight: bold;
                color: #E3E3E3;
            }
            QLabel#header_subtitle {
                background-color: transparent;
                font-size: 9pt;
                color: #8E918F;
            }
            QLabel:disabled {
                background-color: transparent;
                color: #5E6266;
            }
            QLineEdit {
                background-color: #131314;
                border: 1px solid #444746;
                border-radius: 8px;
                padding: 9px 12px;
                color: #E3E3E3;
                font-size: 10pt;
                selection-background-color: #A8C7FA;
                selection-color: #042E6F;
            }
            QLineEdit:focus {
                border: 2px solid #A8C7FA;
                background-color: #1A1B1E;
            }
            QComboBox {
                background-color: #131314;
                border: 1px solid #444746;
                border-radius: 8px;
                padding: 8px 12px;
                color: #E3E3E3;
                font-size: 10pt;
            }
            QComboBox:hover {
                border-color: #8E918F;
            }
            QComboBox:focus {
                border: 2px solid #A8C7FA;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background-color: #1E1F20;
                border: 1px solid #444746;
                border-radius: 8px;
                selection-background-color: #333538;
                selection-color: #A8C7FA;
                color: #E3E3E3;
                padding: 4px;
            }
            QComboBox:disabled {
                background-color: #18191A;
                border: 1px solid #282A2C;
                color: #5E6266;
            }
            QPushButton {
                background-color: #2D2F31;
                color: #E3E3E3;
                border: 1px solid #444746;
                border-radius: 8px;
                padding: 8px 14px;
                font-weight: 600;
                font-size: 9.5pt;
            }
            QPushButton:hover {
                background-color: #37393B;
                border-color: #8E918F;
            }
            QPushButton:pressed {
                background-color: #444746;
            }
            QPushButton#btn_toggle {
                background-color: #6DD58C;
                color: #0A3818;
                border: none;
                border-radius: 24px;
                padding: 13px;
                font-weight: bold;
                font-size: 11pt;
            }
            QPushButton#btn_toggle:hover {
                background-color: #81C995;
            }
            QPushButton#btn_toggle[running="true"] {
                background-color: #F28B82;
                color: #601410;
            }
            QPushButton#btn_toggle[running="true"]:hover {
                background-color: #F6AEA9;
            }
            QSlider {
                background-color: transparent;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #444746;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #A8C7FA;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #A8C7FA;
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: #D3E3FD;
            }
            QProgressBar {
                background-color: #131314;
                border: 1px solid #333538;
                border-radius: 6px;
                text-align: center;
                height: 10px;
            }
            QProgressBar::chunk {
                background-color: #6DD58C;
                border-radius: 5px;
            }
        """)
        
        main_layout = QVBoxLayout()
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(24, 20, 24, 24)
        self.setLayout(main_layout)
        
        # 1. Google Material Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        
        title_box = QHBoxLayout()
        title_box.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        logo_label = QLabel("✨")
        logo_label.setFont(QFont("Google Sans", 14))
        title_box.addWidget(logo_label)
        
        title_label = QLabel("Game Voice Subtitles")
        title_label.setObjectName("header_title")
        title_box.addWidget(title_label)
        
        badge_label = QLabel("Gemini Flash")
        badge_label.setStyleSheet("""
            background-color: #042E6F;
            color: #D3E3FD;
            border-radius: 6px;
            padding: 3px 8px;
            font-size: 8pt;
            font-weight: bold;
        """)
        title_box.addWidget(badge_label)
        title_box.addStretch()
        
        header_layout.addLayout(title_box)
        
        subtitle_label = QLabel("실시간 로컬 Whisper STT & Gemini 다국어 번역 오버레이")
        subtitle_label.setObjectName("header_subtitle")
        header_layout.addWidget(subtitle_label)
        
        main_layout.addLayout(header_layout)
        
        # 2. Material Card Container
        card_frame = QFrame()
        card_frame.setObjectName("card_container")
        card_layout = QVBoxLayout(card_frame)
        card_layout.setSpacing(14)
        card_layout.setContentsMargins(16, 16, 16, 16)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        
        # Form 1: API Key
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Google AI Studio API Key 입력")
        
        api_layout = QHBoxLayout()
        api_layout.setSpacing(6)
        api_layout.addWidget(self.api_key_input)
        
        self.btn_show_key = QPushButton("보기")
        self.btn_show_key.setFixedWidth(56)
        self.btn_show_key.clicked.connect(self.toggle_key_visibility)
        api_layout.addWidget(self.btn_show_key)
        
        self.btn_save_key = QPushButton("저장")
        self.btn_save_key.setFixedWidth(56)
        self.btn_save_key.setStyleSheet("background-color: #042E6F; color: #D3E3FD; border-color: #0842A0;")
        self.btn_save_key.clicked.connect(self.save_api_key)
        api_layout.addWidget(self.btn_save_key)
        
        form_layout.addRow("Gemini API Key:", api_layout)
        
        # Form 2: Audio Device Selection
        self.device_combo = QComboBox()
        self.refresh_devices()
        form_layout.addRow("오디오 장치 (출력):", self.device_combo)
        
        # Form 3: Translation Mode & Language Selection
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("외국어만 번역 (한국어 음성 무시)", "foreign_only")
        self.mode_combo.addItem("지정한 외국어만 번역", "specific")
        self.mode_combo.addItem("모든 음성 자막 (한국어 받아쓰기 + 외국어 번역)", "all")
        self.mode_combo.currentIndexChanged.connect(self.update_translation_config)
        form_layout.addRow("번역 동작 모드:", self.mode_combo)

        self.source_lang_label = QLabel("지정 번역 대상 언어:")
        self.source_lang_combo = QComboBox()
        for lang in ["일본어", "중국어", "영어", "스페인어", "독일어", "프랑스어", "러시아어"]:
            self.source_lang_combo.addItem(lang, lang)
        self.source_lang_combo.currentIndexChanged.connect(self.update_translation_config)
        form_layout.addRow(self.source_lang_label, self.source_lang_combo)

        # Form 4: Sensitivity Threshold
        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setMinimum(1)
        self.threshold_slider.setMaximum(50)
        self.threshold_slider.setValue(3)  # Default 3/1000 = 0.003
        self.threshold_slider.valueChanged.connect(self.update_threshold_label)
        
        self.threshold_label = QLabel("0.003 (민감도)")
        self.threshold_label.setStyleSheet("color: #8E918F; font-size: 9pt;")
        
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(self.threshold_slider)
        threshold_layout.addWidget(self.threshold_label)
        form_layout.addRow("음성 감지 임계값:", threshold_layout)

        # Form 5: Font Size Slider
        self.font_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_size_slider.setMinimum(16)
        self.font_size_slider.setMaximum(48)
        self.font_size_slider.setValue(24)
        self.font_size_slider.valueChanged.connect(self.update_font_size_label)
        
        self.font_size_label = QLabel("24pt")
        self.font_size_label.setStyleSheet("color: #8E918F; font-size: 9pt;")
        
        font_layout = QHBoxLayout()
        font_layout.addWidget(self.font_size_slider)
        font_layout.addWidget(self.font_size_label)
        form_layout.addRow("자막 글꼴 크기:", font_layout)
        
        # Form 6: Audio Level Bar
        self.level_bar = QProgressBar()
        self.level_bar.setMinimum(0)
        self.level_bar.setMaximum(100)
        self.level_bar.setValue(0)
        self.level_bar.setTextVisible(False)
        form_layout.addRow("스피커 출력 레벨:", self.level_bar)
        
        card_layout.addLayout(form_layout)
        main_layout.addWidget(card_frame)

        # 3. Status Text & Action Button
        self.status_label = QLabel("상태: 정지됨")
        self.status_label.setStyleSheet("color: #8E918F; font-size: 9pt; font-weight: normal;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.status_label)
        
        # Material Filled Toggle Button (Start / Stop)
        self.btn_toggle = QPushButton("시작")
        self.btn_toggle.setObjectName("btn_toggle")
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.setProperty("running", "false")
        self.btn_toggle.clicked.connect(self.toggle_running)
        main_layout.addWidget(self.btn_toggle)
        
        # Level meter decay timer (Smooth rendering)
        self.level_timer = QTimer(self)
        self.level_timer.timeout.connect(self.decay_level)
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
        
    def get_threshold(self) -> float:
        return self.threshold_slider.value() / 1000.0

    def update_translation_config(self):
        mode = self.mode_combo.currentData() or "foreign_only"
        source_lang = self.source_lang_combo.currentData() or "영어"
        
        # Show/hide/disable source lang combo depending on mode
        is_specific = (mode == "specific")
        self.source_lang_combo.setEnabled(is_specific)
        if hasattr(self, 'source_lang_label'):
            self.source_lang_label.setEnabled(is_specific)
        
        # Update STT Engine
        self.stt_engine.set_translation_config(mode=mode, source_lang=source_lang, target_lang="한국어")
        
        # Save to .env
        self.save_env_var("TRANSLATION_MODE", mode)
        self.save_env_var("SOURCE_LANG", source_lang)

    def save_env_var(self, key: str, val: str):
        try:
            if not os.path.exists(self.env_path):
                with open(self.env_path, "w", encoding="utf-8") as f:
                    f.write("")
            set_key(self.env_path, key, str(val))
        except Exception as e:
            print(f"[Config Warning] 환경 변수 저장 실패 ({key}={val}): {e}")

    def update_font_size_label(self):
        val = self.font_size_slider.value()
        self.font_size_label.setText(f"{val}pt")
        self.font_size_changed.emit(val)
        self.save_env_var("FONT_SIZE", str(val))

    def save_api_key(self):
        key = self.api_key_input.text().strip()
        if not key:
            self.status_label.setText("오류: 빈 API Key는 저장할 수 없습니다.")
            return
            
        self.save_env_var("GEMINI_API_KEY", key)
        self.stt_engine.set_api_key(key)
        self.status_label.setText("상태: API Key 저장 완료 ✓")
        
    def load_settings(self):
        load_dotenv(dotenv_path=self.env_path, override=True)
        
        # 1. API Key
        key = os.getenv("GEMINI_API_KEY", "")
        if key:
            self.api_key_input.setText(key)
            self.stt_engine.set_api_key(key)
            
        # 2. Font Size
        font_val = os.getenv("FONT_SIZE", "24")
        try:
            val = int(font_val)
            self.font_size_slider.setValue(val)
            self.font_size_label.setText(f"{val}pt")
        except ValueError:
            pass
            
        # 3. Translation Mode
        mode = os.getenv("TRANSLATION_MODE", "foreign_only")
        idx = self.mode_combo.findData(mode)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)
            
        # 4. Source Language
        lang = os.getenv("SOURCE_LANG", "일본어")
        idx = self.source_lang_combo.findData(lang)
        if idx >= 0:
            self.source_lang_combo.setCurrentIndex(idx)
            
        self.update_translation_config()
                        
    def toggle_running(self):
        if not self.is_running:
            # Starting
            key = self.api_key_input.text().strip()
            if not key:
                self.status_label.setText("오류: API Key를 먼저 저장하거나 입력하세요.")
                return
                
            self.is_running = True
            self.btn_toggle.setText("중지")
            self.btn_toggle.setProperty("running", "true")
            self.btn_toggle.style().polish(self.btn_toggle)
            self.status_label.setText("상태: 실시간 오디오 캡처 작동 중 ●")
            
            # Start signals
            device_idx = self.device_combo.currentData()
            if device_idx is None:
                device_idx = -1
            threshold = self.get_threshold()
            self.start_requested.emit(device_idx, threshold)
            
            # Start level decay timer
            self.level_timer.start(50)
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
            
    @pyqtSlot(float)
    def update_audio_level(self, rms_val: float):
        """Thread-safe slot called via Qt Signal to update audio volume meter."""
        scaled = int(rms_val * 1000)
        self.current_level = min(max(scaled, 0), 100)
        self.level_bar.setValue(self.current_level)
        
    def decay_level(self):
        # Smoothly decay the meter level
        self.current_level = max(0, int(self.current_level) - 8)
        self.level_bar.setValue(self.current_level)
        
    @pyqtSlot(str)
    def show_error(self, message: str):
        self.status_label.setText(f"오류: {message}")
        
    def closeEvent(self, event):
        self.stop_requested.emit()
        event.accept()
