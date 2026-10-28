import os
import sys

_venv_site = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv", "Lib", "site-packages")
if not getattr(sys, "frozen", False) and os.path.isdir(_venv_site) and _venv_site not in sys.path:
    sys.path.insert(0, _venv_site)
    sys.modules.pop("google", None)

from google import genai
import base64
import io
import time
import re
import site
import threading
import functools
import numpy as np
from dotenv import load_dotenv, find_dotenv

def get_env_path() -> str:
    """Returns reliable path to .env file whether running in dev or frozen .exe."""
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), ".env")
    found = find_dotenv()
    return found if found else os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

load_dotenv(dotenv_path=get_env_path(), override=True)

# Register NVIDIA CUDA/cuBLAS/cuDNN DLL paths on Windows
def _add_nvidia_dll_directories():
    if sys.platform == "win32":
        bases = [b for b in (getattr(sys, '_MEIPASS', None), _venv_site, *site.getsitepackages(), getattr(sys, 'prefix', None)) if b]
        for base in bases:
            for sub in ['cublas', 'cudnn', 'cuda_nvrtc', 'cuda_runtime']:
                dll_dir = os.path.join(base, 'nvidia', sub, 'bin')
                if os.path.isdir(dll_dir):
                    try:
                        os.add_dll_directory(dll_dir)
                        if dll_dir not in os.environ.get('PATH', ''):
                            os.environ['PATH'] = dll_dir + os.pathsep + os.environ.get('PATH', '')
                    except Exception:
                        pass

_add_nvidia_dll_directories()

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    print("[STT Warning] faster-whisper 라이브러리를 불러올 수 없습니다. pure Gemini 모드로 동작합니다.")

LANG_CODE_MAP = {
    "영어": "en", "일본어": "ja", "중국어": "zh", "스페인어": "es",
    "독일어": "de", "프랑스어": "fr", "러시아어": "ru", "한국어": "ko"
}

WHISPER_MODEL_OPTIONS = [
    ("large-v3-turbo", "고성능 (large-v3-turbo · RTX GPU 권장)"),
    ("small", "중사양 (small · 보급형 GPU/CPU 균형)"),
    ("base", "저사양 (base · 내장그래픽/구형 CPU 권장)"),
    ("tiny", "초저사양 (tiny · 최소 메모리/최고 속도)"),
    ("cloud_only", "클라우드 전용 (로컬 GPU/CPU 미사용 · Gemini 직접 번역)"),
]

SYSTEM_INSTRUCTION = (
    "너는 FPS/배틀로얄(에이펙스 레전드, 발로란트, 오버워치 등) 게임 보이스 채팅 실시간 번역기다. "
    "외국어 보이스 브리핑 텍스트를 게임 문맥에 맞는 자연스럽고 직관적인 한국어 구어체로 번역한다. "
    "절대로 설명, 마크다운, 따옴표, 원문을 출력하지 말고 오직 번역된 한국어 결과만 단 한 줄로 출력하라. "
    "만약 입력된 텍스트가 의미 없는 감탄사, 비음성 잡음, 'Thank you for watching' 등의 영상 엔딩 문구인 경우 아무것도 출력하지 마라."
)

FLASH_MODEL_POOL = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
]

HALLUCINATION_PATTERNS = [
    r"thank\s+you\s+for\s+watching",
    r"thanks\s+for\s+watching",
    r"please\s+subscribe",
    r"like\s+and\s+subscribe",
    r"subtitles\s+by",
    r"transcribed\s+by",
    r"translated\s+by",
    r"mbc\s*뉴스",
    r"시청해\s*주셔서\s*감사합니다",
    r"구독과\s*좋아요",
    r"끝까지\s*시청",
    r"ご視聴ありがとうございました",
    r"チャンネル登録",
    r"感谢观看",
    r"谢谢收看",
]
HALLUCINATION_REGEX = re.compile("|".join(HALLUCINATION_PATTERNS), re.IGNORECASE)


def is_hallucination(text: str) -> bool:
    """Detects and filters out Whisper hallucinations, noise loops, and artifact texts."""
    clean = text.strip().lower()
    if (len(clean) < 2 and not re.search(r'[가-힣一-龥]', clean)) or HALLUCINATION_REGEX.search(clean):
        return True
    words = clean.split()
    if len(words) >= 4 and len(set(words)) <= 2:
        return True
    non_alpha = re.sub(r'[\w\s가-힣一-龥ぁ-んァ-ヶ]', '', clean)
    return len(non_alpha) > len(clean) * 0.5


class GeminiSTTEngine:
    def __init__(self, api_key=None, whisper_model_name=None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self._client = None
        if self.api_key:
            try:
                self._client = genai.Client(api_key=self.api_key)
                print("[STT] Gemini API 키 설정 완료.")
            except Exception as e:
                print(f"[STT Error] Gemini API 키 설정 실패: {e}")
        else:
            print("[STT Warning] GEMINI_API_KEY가 설정되지 않았습니다.")
            
        self._config_lock = threading.Lock()
        self._whisper_lock = threading.Lock()
        
        self.mode = os.getenv("TRANSLATION_MODE", "foreign_only")
        self.source_lang = os.getenv("SOURCE_LANG", "일본어")
        self.target_lang = os.getenv("TARGET_LANG", "한국어")
        
        self.whisper_model_name = whisper_model_name or os.getenv("WHISPER_MODEL", "large-v3-turbo")
        self.whisper_model = None
        self.whisper_status = "uninitialized"
        
        self.init_whisper()
        
    def init_whisper(self):
        """Initializes faster-whisper model asynchronously with GPU and CPU fallback."""
        if self.whisper_model_name == "cloud_only":
            with self._whisper_lock:
                self.whisper_model = None
                self.whisper_status = "cloud_only"
            print("[STT] 클라우드 전용 모드: 로컬 Whisper 모델을 로드하지 않습니다.")
            return

        if not WHISPER_AVAILABLE:
            self.whisper_status = "failed"
            return

        target_model = self.whisper_model_name
        self.whisper_status = "loading"

        def _load():
            try:
                import ctranslate2
                if ctranslate2.get_cuda_device_count() > 0:
                    print(f"[STT] GPU(CUDA FP16) faster-whisper({target_model}) 로딩 중...")
                    loaded_model = WhisperModel(target_model, device="cuda", compute_type="float16")
                    dummy = np.zeros(16000, dtype=np.float32)
                    list(loaded_model.transcribe(dummy, beam_size=1)[0])
                    with self._whisper_lock:
                        if self.whisper_model_name != target_model:
                            return
                        self.whisper_model = loaded_model
                        self.whisper_status = "ready"
                    print(f"[STT] faster-whisper ({target_model}) [CUDA FP16] 로딩 완료!")
                    return
            except Exception as e:
                print(f"[STT Warning] CUDA GPU 로딩 실패 (CPU int8로 전환): {e}")

            if self.whisper_model_name != target_model:
                return
            try:
                print(f"[STT] CPU(int8) faster-whisper({target_model}) 로딩 중...")
                loaded_model = WhisperModel(target_model, device="cpu", compute_type="int8")
                with self._whisper_lock:
                    if self.whisper_model_name != target_model:
                        return
                    self.whisper_model = loaded_model
                    self.whisper_status = "ready"
                print(f"[STT] faster-whisper ({target_model}) [CPU int8] 로딩 완료!")
            except Exception as ex:
                print(f"[STT Error] faster-whisper CPU 로딩 실패: {ex}")
                with self._whisper_lock:
                    if self.whisper_model_name != target_model:
                        return
                    self.whisper_status = "failed"

        threading.Thread(target=_load, daemon=True).start()

    def set_whisper_model(self, model_name: str):
        if model_name == self.whisper_model_name and self.whisper_status in ("ready", "loading", "cloud_only"):
            return
        with self._whisper_lock:
            self.whisper_model_name = model_name
            self.whisper_model = None
        self.init_whisper()

    def _get_client(self):
        with self._config_lock:
            if not self.api_key:
                self.api_key = os.getenv("GEMINI_API_KEY")
            if not self.api_key:
                raise ValueError("Gemini API Key가 설정되지 않았습니다.")
            if self._client is None:
                self._client = genai.Client(api_key=self.api_key)
            return self._client

    def set_api_key(self, api_key: str):
        with self._config_lock:
            self.api_key = api_key
            try:
                self._client = genai.Client(api_key=api_key)
                self._translate_cached.cache_clear()
                print("[STT] Gemini API 키가 새로 설정되었습니다.")
            except Exception as e:
                self._client = None
                print(f"[STT Error] API 키 설정 실패: {e}")

    def set_translation_config(self, mode="foreign_only", source_lang="일본어", target_lang="한국어"):
        with self._config_lock:
            self.mode = mode
            self.source_lang = source_lang
            self.target_lang = target_lang
            print(f"[STT] 번역 설정 변경: 모드={mode}, 지정 언어={source_lang}, 목표 언어={target_lang}")

    def get_config(self):
        with self._config_lock:
            return self.mode, self.source_lang, self.target_lang

    def transcribe(self, wav_bytes: bytes) -> str:
        """Transcribes and translates speech using Hybrid (Whisper + Gemini) or Cloud."""
        try:
            if self.whisper_status == "loading":
                print("[STT] 로컬 Whisper 모델 로딩 대기 중...")
                return ""
                
            with self._whisper_lock:
                whisper_model = self.whisper_model
                if whisper_model is not None:
                    try:
                        return self._transcribe_hybrid(wav_bytes, whisper_model)
                    except Exception as e:
                        print(f"[STT Hybrid Error] {e} -> Gemini Audio API로 폴백")

            return self._transcribe_gemini_audio(wav_bytes)
        except Exception as e:
            print(f"[STT Error] 음성 변환 예외: {e}")
            return ""

    @functools.lru_cache(maxsize=500)
    def _translate_cached(self, text: str, detected_lang: str, target_lang: str) -> str:
        prompt = f"다음 게임 보이스({detected_lang})를 {target_lang}로 번역하라: \"{text}\""
        client = self._get_client()
        
        for model_name in FLASH_MODEL_POOL:
            try:
                interaction = client.interactions.create(
                    model=model_name,
                    system_instruction=SYSTEM_INSTRUCTION,
                    input=prompt,
                    generation_config={"thinking_level": "minimal", "max_output_tokens": 150},
                    store=False,
                )
                cleaned = (getattr(interaction, "output_text", None) or "").strip().strip('"').strip("'")
                return "" if (not cleaned or is_hallucination(cleaned)) else cleaned
            except Exception as ex:
                if "429" in str(ex) or "Quota exceeded" in str(ex) or "RESOURCE_EXHAUSTED" in str(ex):
                    print(f"[Gemini 429] [{model_name}] 쿼터 초과 -> 다음 모델 전환")
                    continue
                print(f"[Gemini Error on {model_name}]: {ex}")
        raise RuntimeError("All models failed")

    def translate_text(self, text: str, detected_lang: str) -> str:
        clean_text = text.strip()
        if not clean_text or is_hallucination(clean_text):
            return ""
        _, _, target_lang = self.get_config()
        try:
            return self._translate_cached(clean_text, detected_lang, target_lang)
        except Exception as e:
            print(f"[STT Translation Fallback] {e}")
            return clean_text

    def _transcribe_hybrid(self, wav_bytes: bytes, whisper_model) -> str:
        mode, source_lang, target_lang = self.get_config()
        audio_stream = io.BytesIO(wav_bytes)
        
        segments, info = whisper_model.transcribe(
            audio_stream,
            beam_size=1,
            temperature=0.0,
            condition_on_previous_text=False,
            no_speech_threshold=0.5,
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=300, speech_pad_ms=200)
        )
        
        valid_texts = []
        for segment in segments:
            if segment.no_speech_prob > 0.6 or segment.avg_logprob < -1.2:
                continue
            text = segment.text.strip()
            if text and not is_hallucination(text):
                valid_texts.append(text)
            
        if not valid_texts:
            return ""
            
        stt_text = " ".join(valid_texts).strip()
        detected_lang = info.language
        
        if not stt_text or is_hallucination(stt_text):
            return ""
            
        print(f"[Whisper STT] 감지 언어: {detected_lang}, 텍스트: '{stt_text}'")
        
        if mode == "foreign_only":
            if detected_lang == "ko":
                return ""
        elif mode == "specific":
            target_code = LANG_CODE_MAP.get(source_lang, "en")
            if detected_lang != target_code:
                return ""
        else:
            if detected_lang == "ko":
                return stt_text

        translated = self.translate_text(stt_text, detected_lang)
        if translated:
            print(f"[Translation] 번역 완료: '{translated}'")
        return translated

    def _transcribe_gemini_audio(self, wav_bytes: bytes) -> str:
        mode, source_lang, target_lang = self.get_config()
        audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
        
        if mode == "foreign_only":
            rule_text = f"1. 음성이 {target_lang}인 경우 아무것도 출력하지 말 것.\n2. 외국어인 경우 {target_lang}(으)로 번역할 것."
        elif mode == "specific":
            rule_text = f"1. 음성이 '{source_lang}'인 경우만 {target_lang}(으)로 번역할 것.\n2. 그 외는 아무것도 출력하지 말 것."
        else:
            rule_text = f"1. {target_lang} 음성은 받아쓰기, 외국어는 {target_lang}(으)로 번역할 것."

        prompt = f"게임 보이스 자막 변환 엔진입니다. 오직 번역/받아쓰기 결과만 출력하세요.\n{rule_text}"
        
        try:
            client = self._get_client()
        except Exception as e:
            print(f"[STT Error] Gemini 클라이언트 초기화 실패: {e}")
            return ""

        for model_name in FLASH_MODEL_POOL:
            try:
                interaction = client.interactions.create(
                    model=model_name,
                    system_instruction=SYSTEM_INSTRUCTION,
                    input=[
                        {"type": "text", "text": prompt},
                        {"type": "audio", "data": audio_b64, "mime_type": "audio/wav"},
                    ],
                    generation_config={"thinking_level": "minimal", "max_output_tokens": 150},
                    store=False,
                )
                res_text = (getattr(interaction, "output_text", None) or "").strip().strip('"').strip("'")
                return "" if (not res_text or is_hallucination(res_text)) else res_text
            except Exception as e:
                if "429" in str(e) or "Quota exceeded" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    print(f"[Gemini 429] [{model_name}] 쿼터 초과 -> 다음 모델 전환")
                    continue
                print(f"[Gemini Audio Error on {model_name}]: {e}")
        return ""
