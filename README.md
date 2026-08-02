# 🎮 게임 보이스 실시간 자막 & 번역 오버레이 (Game Voice Subtitle Overlay)

Windows 환경에서 게임 플레이 중 상대방이나 팀원의 **스피커 오디오(에이펙스 레전드, 발로란트, 디스코드 등)**를 실시간 캡처하여, **로컬 `faster-whisper` (`large-v3-turbo`) STT 엔진**과 **Google Gemini API 번역 엔진**을 조합해 화면상에 투명 자막 오버레이로 출력해 주는 파이썬 애플리케이션입니다.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.10%2B-green.svg)
![PyQt6](https://img.shields.io/badge/PyQt-6-purple.svg)

---

## ✨ 핵심 기능 (Key Features)

- ⚡ **하이브리드 STT & 번역 파이프라인**:
  - **로컬 STT (`faster-whisper` `large-v3-turbo`)**: RTX GPU(CUDA FP16)를 활용하여 0.1초 내로 일본어/중국어/영어 보이스 브리핑을 텍스트로 가공.
  - **Gemini API 초고속 번역**: 무음, 소음, 한국어 음성은 **로컬에서 0-토큰으로 필터링**하며, 외국어 브리핑만 Gemini 3.1 Flash Lite로 빠르게 한국어 번역.
- 🎯 **게임 맞춤형 클릭 투과(Click-through) 오버레이**:
  - 게임 플레이 및 마우스 조작을 가로채지 않는 `WindowTransparentForInput` 투명 레이어.
  - Smooth Fade In/Out 애니메이션 내장.
- 🔊 **WASAPI 루프백 오디오 캡처**:
  - 별도 가상 마이크/사운드 카드 설치 없이 스피커 출력 소리를 직접 캡처.
- 🎛️ **다양한 번역 동작 모드**:
  - `외국어만 번역`: 한국어 음성은 무시하고 외국어 브리핑만 자막 출력.
  - `지정한 외국어만 번역`: 일본어, 중국어 등 특정 선택 언어만 번역.
  - `모든 음성 자막`: 한국어 받아쓰기 + 외국어 번역 통합 제공.

---

## 🛠️ 요구 사항 (Requirements)

- **OS**: Windows 10 / 11 (64-bit)
- **Python**: Python 3.10 이상
- **GPU (선택/권장)**: NVIDIA GeForce GTX/RTX 계열 (CUDA 지원)
  *(CUDA가 없을 경우 CPU int8 모드로 자동 폴백 처리됩니다.)*

---

## 🚀 시작하기 (Getting Started)

### 1. 저장소 클론 및 패키지 설치
```bash
git clone https://github.com/your-username/game-voice-subtitles.git
cd game-voice-subtitles
pip install -r requirements.txt
```

### 2. 환경 변수 설정 (.env)
`.env.example` 파일을 참고하여 프로젝트 루트 폴더에 `.env` 파일을 생성하고 Gemini API Key를 입력합니다.

```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
TRANSLATION_MODE=foreign_only
SOURCE_LANG=일본어
TARGET_LANG=한국어
FONT_SIZE=24
```
*(Gemini API Key는 [Google AI Studio](https://aistudio.google.com/)에서 무료로 발급받을 수 있으며, 프로그램 실행 후 컨트롤 패널 GUI에서도 직접 입력 및 저장 가능합니다.)*

### 3. 프로그램 실행
```bash
python main.py
```

---

## 📦 독립 실행 파일 빌드 (.exe)

PyInstaller를 이용하여 단일 `.exe` 실행 파일로 패키징할 수 있습니다.

```bash
pip install pyinstaller
python -m PyInstaller GameVoiceOverlay.spec --noconfirm
```
빌드가 완료되면 `dist/GameVoiceOverlay.exe` 파일이 생성됩니다.

---

## 📜 라이선스 (License)

This project is licensed under the MIT License.
