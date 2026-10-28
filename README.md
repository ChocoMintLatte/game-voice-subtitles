# 🎮 게임 보이스 실시간 자막 & 번역 오버레이 (Game Voice Subtitle Overlay)

Windows 환경에서 게임 플레이 중 상대방이나 팀원의 **스피커 오디오(에이펙스 레전드, 발로란트, 오버워치, 디스코드 등)**를 실시간 캡처하여, **로컬 `faster-whisper` STT 엔진**과 **Google Gemini (`google-genai` Interactions API) 번역 엔진**을 조합해 화면상에 투명 자막 오버레이로 출력해 주는 애플리케이션입니다.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%2F%2011-blue.svg)
![Python](https://img.shields.io/badge/Python-3.10%2B-green.svg)
![UI](https://img.shields.io/badge/UI-Google%20Material%203-blueviolet.svg)

---

## ✨ 핵심 기능 (Key Features)

- 💻 **PC 사양별 5단계 맞춤형 음성 인식/번역 모델 지원**:
  - **`고성능 (large-v3-turbo)`**: RTX 외장 GPU(CUDA FP16) 권장, 최고 수준의 다국어 인식 품질.
  - **`중사양 (small)`**: 보급형 GPU 및 일반 CPU 환경을 위한 균형 프리셋.
  - **`저사양 (base)`**: 구형 CPU 및 내장 그래픽(iGPU) 환경 권장.
  - **`초저사양 (tiny)`**: 최소 메모리 점유율 및 최고 처리 속도.
  - **`클라우드 전용 (cloud_only)`**: 로컬 GPU/CPU 자원을 전혀 사용하지 않고 Google Gemini 클라우드로 오디오를 직접 실시간 번역 (초저사양 PC 프레임 드랍 0%).
- ⚡ **하이브리드 고속 STT & 번역 파이프라인**:
  - **최신 Gemini Interactions API 멀티 모델 페일오버**: `gemini-3.5-flash-lite`, `gemini-3.8-flash`, `gemini-3.1-flash-lite` 풀을 구성하여 무료 티어 429 한도를 우회하고 끊김 없는 실시간 번역 제공.
  - **인메모리 LRU 번역 캐시**: 자주 나오는 브리핑("Push", "One shot", "Sniper" 등)은 0-토큰(0ms)으로 즉시 자막 표출 (실패 응답 캐싱 방지 적용).
  - **4중 환각 방지 필터 & 한자권 단문자 콜아웃 보존**: 게임 효과음/잡음에서 발생하는 환각 자막은 차단하면서, 일본어·중국어 1글자 핵심 브리핑(`敵`, `右`, `左`, `上`, `下` 등)은 정확히 인식.
  - **Drop-Oldest 백프레셔 & 200ms 발화 오버랩**: 교전 중 보이스가 몰려도 자막이 밀리지 않고 최신 브리핑을 우선 처리하며, 장문 분할 시 단어 경계 잘림 방지.
- 🎯 **게임 맞춤형 클릭 투과(Click-through) 오버레이**:
  - 게임 플레이 및 마우스 조작을 가로채지 않는 `WindowTransparentForInput` 투명 레이어.
  - Smooth Fade In/Out 애니메이션 내장.
- 🔊 **WASAPI 루프백 오디오 캡처 & 실시간 민감도 조절**:
  - 별도 가상 마이크 설치 없이 스피커 출력 소리를 직접 캡처하며, 에일리어싱 방지(Anti-aliasing) 리샘플링 내장.
  - 캡처 작동 중에도 음성 감지 임계값(Threshold)과 자막 글꼴 크기를 실시간으로 조절하고 `.env`에 자동 저장.
- 🎛️ **다양한 번역 동작 모드**:
  - `외국어만 번역`: 한국어 음성은 무시하고 외국어 브리핑만 자막 출력.
  - `지정한 외국어만 번역`: 일본어, 중국어 등 특정 선택 언어만 번역.
  - `모든 음성 자막`: 한국어 받아쓰기 + 외국어 번역 통합 제공.
- 🎨 **Google Material 3 Dark Theme UI**:
  - Google AI Studio 감성의 모던하고 깔끔한 다크 테마 컨트롤 패널.

---

## 🚀 빠른 시작 (가장 쉬운 실행 방법)

> **파이썬이나 복잡한 개발 도구가 설치되어 있지 않아도 `.exe` 파일 하나만으로 바로 실행할 수 있습니다.**

### 1. 실행 파일 다운로드
공개 배포 저장소 `game-voice-subtitles-app`의 [릴리스 페이지](https://github.com/ChocoMintLatte/game-voice-subtitles-app/releases/tag/v1.0.0)에서 **[`GameVoiceOverlay.exe`](https://github.com/ChocoMintLatte/game-voice-subtitles-app/releases/download/v1.0.0/GameVoiceOverlay.exe)** 파일을 다운로드합니다.

### 2. 프로그램 실행 및 설정
1. 다운로드받은 `GameVoiceOverlay.exe`를 더블 클릭하여 실행합니다.
2. [Google AI Studio](https://aistudio.google.com/)에서 무료로 발급받은 **Gemini API Key**를 컨트롤 패널의 입력창에 넣고 **[저장]** 버튼을 누릅니다.
3. 본인 PC 사양에 맞는 **음성 인식/번역 모델**(`고성능` / `중사양` / `저사양` / `초저사양` / `클라우드 전용`)을 선택합니다.
   *(모든 설정은 실행 파일 위치의 `.env` 파일에 자동 보관되어 다음 실행 시 그대로 유지됩니다.)*
4. **[시작]** 버튼을 누르면 실시간 자막 오버레이가 활성화됩니다!

> **💡 팁 (인게임 설정)**: 게임 그래픽 옵션에서 화면 모드를 **`테두리 없는 창모드(Borderless Windowed)`** 또는 **`전체 창모드`**로 설정하시면 전체화면 게임 플레이 중에도 실시간 자막을 편하게 보실 수 있습니다.

---

## 🛠️ 개발자용 소스 코드 실행 방법

### 1. 저장소 클론 및 패키지 설치
```bash
git clone https://github.com/ChocoMintLatte/game-voice-subtitles.git
cd game-voice-subtitles
pip install -r requirements.txt
```

### 2. 프로그램 실행
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
