import os
import sys
from dotenv import load_dotenv, set_key
from stt_engine import get_env_path, WHISPER_MODEL_OPTIONS
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, 
    QPushButton, QComboBox, QSlider, QProgressBar, QFormLayout,
    QGraphicsOpacityEffect, QApplication, QFrame
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont


class SubtitleOverlay(QWidget):
    """Google-styled transparent, click-through, always-on-top subtitle overlay."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
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
        
        self.label = QLabel("")
        self.label.setFont(QFont("Google Sans", 24, QFont.Weight.DemiBold))
        self.label.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                background-color: rgba(19, 19, 20, 0.88);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 16px;
                padding: 14px 32px;
            }
        """)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        self.label.hide()
        layout.addWidget(self.label)
        
        screen = QApplication.primaryScreen().geometry()
        width, height = int(screen.width() * 0.6), 150
        self.setGeometry(int((screen.width() - width) / 2), screen.height() - height - 120, width, height)
        
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)
        
        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.animation.setDuration(250)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.finished.connect(self.on_fade_finished)
        
        self.fade_timer = QTimer(self)
        self.fade_timer.setSingleShot(True)
        self.fade_timer.timeout.connect(self.fade_out)
        
    @pyqtSlot(str)
    def update_subtitle(self, text: str):
        if not text or not text.strip():
            return
            
        self.label.setText(text)
        self.label.show()
        self.fade_timer.stop()
        self.animation.stop()
        
        if self.opacity_effect.opacity() < 1.0:
            self.opacity_effect.setOpacity(1.0)
            self.show()
            
        self.fade_timer.start(5000)
        
    def fade_out(self):
        self.animation.stop()
        self.animation.setStartValue(self.opacity_effect.opacity())
        self.animation.setEndValue(0.0)
        self.animation.start()
        
    def on_fade_finished(self):
        if self.opacity_effect.opacity() == 0.0:
            self.label.hide()
            self.hide()

    @pyqtSlot(int)
    def change_font_size(self, size: int):
        self.label.setFont(QFont("Google Sans", size, QFont.Weight.DemiBold))


class ControlPanel(QWidget):
    start_requested = pyqtSignal(int, float)  # (device_idx, threshold)
    stop_requested = pyqtSignal()
    font_size_changed = pyqtSignal(int)
    threshold_changed = pyqtSignal(float)
    
    def __init__(self, stt_engine, parent=None):
        super().__init__(parent)
        self.stt_engine = stt_engine
        self.is_running = False
        self.env_path = get_env_path()
        self.init_ui()
        self.load_settings()
        
    def init_ui(self):
        self.setWindowTitle("Google AI 게임 보이스 자막 - 컨트롤 패널")
        self.resize(500, 560)
        
        self.setStyleSheet("""
            QWidget { background-color: #131314; color: #E3E3E3; font-family: 'Google Sans', 'Malgun Gothic', sans-serif; }
            QFrame#card_container { background-color: #1E1F20; border: 1px solid #333538; border-radius: 16px; padding: 14px; }
            QLabel { background-color: transparent; font-size: 10pt; color: #C4C7C5; font-weight: 500; }
            QLabel#header_title { font-size: 16pt; font-weight: bold; color: #E3E3E3; }
            QLabel#header_subtitle, QLabel:disabled { font-size: 9pt; color: #8E918F; }
            QLineEdit, QComboBox { background-color: #131314; border: 1px solid #444746; border-radius: 8px; padding: 8px 12px; color: #E3E3E3; font-size: 10pt; }
            QLineEdit:focus, QComboBox:focus { border: 2px solid #A8C7FA; }
            QComboBox QAbstractItemView { background-color: #1E1F20; border: 1px solid #444746; selection-background-color: #333538; color: #E3E3E3; }
            QPushButton { background-color: #2D2F31; color: #E3E3E3; border: 1px solid #444746; border-radius: 8px; padding: 8px 14px; font-weight: 600; font-size: 9.5pt; }
            QPushButton:hover { background-color: #37393B; }
            QPushButton#btn_toggle { background-color: #6DD58C; color: #0A3818; border: none; border-radius: 22px; padding: 12px; font-weight: bold; font-size: 11pt; }
            QPushButton#btn_toggle:hover { background-color: #81C995; }
            QPushButton#btn_toggle[running="true"] { background-color: #F28B82; color: #601410; }
            QSlider { background: transparent; }
            QSlider::groove:horizontal { height: 4px; background: #444746; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #A8C7FA; border-radius: 2px; }
            QSlider::handle:horizontal { background: #A8C7FA; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; }
            QProgressBar { background-color: #131314; border: 1px solid #333538; border-radius: 6px; height: 10px; }
            QProgressBar::chunk { background-color: #6DD58C; border-radius: 5px; }
        """)
        
        main_layout = QVBoxLayout()
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(24, 20, 24, 24)
        self.setLayout(main_layout)
        
        # Header
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
        badge_label.setStyleSheet("background-color: #042E6F; color: #D3E3FD; border-radius: 6px; padding: 3px 8px; font-size: 8pt; font-weight: bold;")
        title_box.addWidget(badge_label)
        title_box.addStretch()
        header_layout.addLayout(title_box)
        
        subtitle_label = QLabel("실시간 로컬 Whisper STT & Gemini 다국어 번역 오버레이")
        subtitle_label.setObjectName("header_subtitle")
        header_layout.addWidget(subtitle_label)
        main_layout.addLayout(header_layout)
        
        # Form Container
        card_frame = QFrame()
        card_frame.setObjectName("card_container")
        card_layout = QVBoxLayout(card_frame)
        card_layout.setSpacing(14)
        card_layout.setContentsMargins(16, 16, 16, 16)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        
        # 1. API Key
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
        
        # 2. Model Selection
        self.whisper_model_combo = QComboBox()
        for model_id, label in WHISPER_MODEL_OPTIONS:
            self.whisper_model_combo.addItem(label, model_id)
        self.whisper_model_combo.currentIndexChanged.connect(self.update_whisper_model)
        form_layout.addRow("음성 인식/번역 모델:", self.whisper_model_combo)

        # 3. Device Selection
        self.device_combo = QComboBox()
        self.refresh_devices()
        form_layout.addRow("오디오 장치 (출력):", self.device_combo)
        
        # 3. Translation Mode
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

        # 4. Sensitivity Threshold
        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setMinimum(1)
        self.threshold_slider.setMaximum(50)
        self.threshold_slider.setValue(3)
        self.threshold_slider.valueChanged.connect(self.update_threshold_label)
        
        self.threshold_label = QLabel("0.003 (민감도)")
        self.threshold_label.setStyleSheet("color: #8E918F; font-size: 9pt;")
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(self.threshold_slider)
        threshold_layout.addWidget(self.threshold_label)
        form_layout.addRow("음성 감지 임계값:", threshold_layout)

        # 5. Font Size
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
        
        # 6. Audio Level Bar
        self.level_bar = QProgressBar()
        self.level_bar.setMinimum(0)
        self.level_bar.setMaximum(100)
        self.level_bar.setValue(0)
        self.level_bar.setTextVisible(False)
        form_layout.addRow("스피커 출력 레벨:", self.level_bar)
        
        card_layout.addLayout(form_layout)
        main_layout.addWidget(card_frame)

        # Status & Toggle Button
        self.status_label = QLabel("상태: 정지됨")
        self.status_label.setStyleSheet("color: #8E918F; font-size: 9pt; font-weight: normal;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.status_label)
        
        self.btn_toggle = QPushButton("시작")
        self.btn_toggle.setObjectName("btn_toggle")
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.setProperty("running", "false")
        self.btn_toggle.clicked.connect(self.toggle_running)
        main_layout.addWidget(self.btn_toggle)
        
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
        self.threshold_changed.emit(val)
        self.save_env_var("THRESHOLD", f"{val:.3f}")

    def update_whisper_model(self):
        model_name = self.whisper_model_combo.currentData() or "large-v3-turbo"
        self.stt_engine.set_whisper_model(model_name)
        self.save_env_var("WHISPER_MODEL", model_name)

    def update_translation_config(self):
        mode = self.mode_combo.currentData() or "foreign_only"
        source_lang = self.source_lang_combo.currentData() or "영어"
        is_specific = (mode == "specific")
        self.source_lang_combo.setEnabled(is_specific)
        self.source_lang_label.setEnabled(is_specific)
        
        self.stt_engine.set_translation_config(mode=mode, source_lang=source_lang, target_lang="한국어")
        self.save_env_var("TRANSLATION_MODE", mode)
        self.save_env_var("SOURCE_LANG", source_lang)

    def save_env_var(self, key: str, val: str):
        try:
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
        key = os.getenv("GEMINI_API_KEY", "")
        if key:
            self.api_key_input.setText(key)
            self.stt_engine.set_api_key(key)
            
        try:
            val = int(os.getenv("FONT_SIZE", "24"))
            self.font_size_slider.setValue(val)
            self.font_size_label.setText(f"{val}pt")
        except ValueError:
            pass
            
        val = os.getenv("THRESHOLD", "0.003")
        try:
            self.threshold_slider.setValue(int(round(float(val) * 1000)))
        except ValueError:
            pass
            
        w_model = os.getenv("WHISPER_MODEL", "large-v3-turbo")
        idx = self.whisper_model_combo.findData(w_model)
        if idx >= 0:
            self.whisper_model_combo.setCurrentIndex(idx)

        mode = os.getenv("TRANSLATION_MODE", "foreign_only")
        idx = self.mode_combo.findData(mode)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)
            
        lang = os.getenv("SOURCE_LANG", "일본어")
        idx = self.source_lang_combo.findData(lang)
        if idx >= 0:
            self.source_lang_combo.setCurrentIndex(idx)
            
        self.update_translation_config()
                        
    def toggle_running(self):
        if not self.is_running:
            key = self.api_key_input.text().strip()
            if not key:
                self.status_label.setText("오류: API Key를 먼저 저장하거나 입력하세요.")
                return
                
            self.is_running = True
            self.btn_toggle.setText("중지")
            self.btn_toggle.setProperty("running", "true")
            self.btn_toggle.style().polish(self.btn_toggle)
            self.status_label.setText("상태: 실시간 오디오 캡처 작동 중 ●")
            
            device_idx = self.device_combo.currentData()
            if device_idx is None:
                device_idx = -1
            threshold = self.threshold_slider.value() / 1000.0
            self.start_requested.emit(device_idx, threshold)
            self.level_timer.start(50)
        else:
            self.is_running = False
            self.btn_toggle.setText("시작")
            self.btn_toggle.setProperty("running", "false")
            self.btn_toggle.style().polish(self.btn_toggle)
            self.status_label.setText("상태: 정지됨")
            self.level_bar.setValue(0)
            self.stop_requested.emit()
            self.level_timer.stop()
            
    @pyqtSlot(float)
    def update_audio_level(self, rms_val: float):
        self.current_level = min(max(int(rms_val * 1000), 0), 100)
        self.level_bar.setValue(self.current_level)
        
    def decay_level(self):
        self.current_level = max(0, int(self.current_level) - 8)
        self.level_bar.setValue(self.current_level)
        
    @pyqtSlot(str)
    def show_error(self, message: str):
        self.status_label.setText(f"오류: {message}")
        
    def closeEvent(self, event):
        self.stop_requested.emit()
        event.accept()
