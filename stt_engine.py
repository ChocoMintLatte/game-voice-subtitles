import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import os
import sys
import io
import time
import re
import site
import threading
import collections
import numpy as np
from dotenv import load_dotenv

def get_env_path() -> str:
    """Returns reliable path to .env file whether running in dev or frozen .exe."""
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, ".env")

# Load env variables safely
load_dotenv(dotenv_path=get_env_path(), override=True)

# Register NVIDIA CUDA/cuBLAS/cuDNN DLL paths on Windows
def _add_nvidia_dll_directories():
    if sys.platform == "win32":
        search_paths = []
        if hasattr(sys, '_MEIPASS'):
            search_paths.append(sys._MEIPASS)
            try:
                os.add_dll_directory(sys._MEIPASS)
                if sys._MEIPASS not in os.environ.get('PATH', ''):
                    os.environ['PATH'] = sys._MEIPASS + os.pathsep + os.environ.get('PATH', '')
            except Exception:
                pass
        try:
            search_paths.extend(site.getsitepackages())
        except Exception:
            pass
        if hasattr(sys, 'prefix'):
            search_paths.append(sys.prefix)
            
        for base in search_paths:
            try:
                os.add_dll_directory(base)
            except Exception:
                pass
            for sub in ['cublas', 'cudnn', 'cuda_nvrtc', 'cuda_runtime']:
                dll_dir = os.path.join(base, 'nvidia', sub, 'bin')
                if os.path.isdir(dll_dir):
                    try:
                        os.add_dll_directory(dll_dir)
                        if dll_dir not in os.environ.get('PATH', ''):
                            os.environ['PATH'] = dll_dir + os.pathsep + os.environ.get('PATH', '')
                        print(f"[STT] NVIDIA DLL 경로 등록: {dll_dir}")
                    except Exception as e:
                        print(f"[STT Warning] DLL 경로 등록 실패 ({dll_dir}): {e}")

_add_nvidia_dll_directories()

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    print("[STT Warning] faster-whisper 라이브러리를 불러올 수 없습니다. pure Gemini 모드로 동작합니다.")

# Language mapping for specific mode
LANG_CODE_MAP = {
    "영어": "en",
    "일본어": "ja",
    "중국어": "zh",
    "스페인어": "es",
    "독일어": "de",
    "프랑스어": "fr",
    "러시아어": "ru",
    "한국어": "ko"
}

# Unrestricted safety settings for gaming vocabulary (kills, guns, slang, etc.)
GAMING_SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

SYSTEM_INSTRUCTION = (
    "너는 FPS/배틀로얄(에이펙스 레전드, 발로란트, 오버워치 등) 게임 보이스 채팅 실시간 번역기다. "
    "외국어 보이스 브리핑 텍스트를 게임 문맥에 맞는 자연스럽고 직관적인 한국어 구어체로 번역한다. "
    "절대로 설명, 마크다운, 따옴표, 원문을 출력하지 말고 오직 번역된 한국어 결과만 단 한 줄로 출력하라. "
    "만약 입력된 텍스트가 의미 없는 감탄사, 비음성 잡음, 'Thank you for watching' 등의 영상 엔딩 문구인 경우 아무것도 출력하지 마라."
)

# Multi-Model Failover Pool (Each has separate 15 RPM free tier quotas -> Total 60+ RPM)
FLASH_MODEL_POOL = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-flash-lite-latest"
]

# Common Whisper Hallucination / Noise Patterns (YouTube bias, repetitive loops, etc.)
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

def is_hallucination(text: str) -> bool:
    """Detects and filters out Whisper hallucinations, noise loops, and artifact texts."""
    clean = text.strip().lower()
    if len(clean) < 2:
        return True
        
    # 1. Regex blacklist matching
    for pat in HALLUCINATION_PATTERNS:
        if re.search(pat, clean):
            return True
            
    # 2. Repetitive single word / short phrase loop check (e.g. "you you you you" or "thank you thank you")
    words = clean.split()
    if len(words) >= 4 and len(set(words)) <= 2:
        return True
        
    # 3. Excessive punctuation or symbol only
    non_alpha = re.sub(r'[\w\s가-힣一-龥ぁ-んァ-ヶ]', '', clean)
    if len(non_alpha) > len(clean) * 0.5:
        return True
        
    return False


class GeminiSTTEngine:
    def __init__(self, api_key=None, whisper_model_name="large-v3-turbo"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                print("[STT] Gemini API 키 설정 완료.")
            except Exception as e:
                print(f"[STT Error] Gemini API 키 설정 실패: {e}")
        else:
            print("[STT Warning] GEMINI_API_KEY가 설정되지 않았습니다. API 키를 수동으로 입력하거나 .env 파일에 작성해야 합니다.")
            
        # Model instances and failover cooldowns
        self._models = {}
        self._model_cooldowns = {}  # {model_name: cooldown_until_timestamp}
        
        # In-memory LRU Translation Cache (Max 500 entries)
        self._translation_cache = collections.OrderedDict()
        self._cache_lock = threading.Lock()
        
        # Thread locks
        self._config_lock = threading.Lock()
        self._whisper_lock = threading.Lock()
        
        # Translation configuration
        self.mode = os.getenv("TRANSLATION_MODE", "foreign_only")  # "all", "foreign_only", "specific"
        self.source_lang = os.getenv("SOURCE_LANG", "일본어")
        self.target_lang = os.getenv("TARGET_LANG", "한국어")
        
        # Whisper model setup & status
        self.whisper_model_name = whisper_model_name
        self.whisper_model = None
        self.whisper_device = "cuda"
        self.whisper_compute_type = "float16"
        self.whisper_status = "uninitialized"  # "loading", "ready", "failed"
        
        self.init_whisper()
        
    def init_whisper(self):
        """Initializes faster-whisper model asynchronously with GPU (CUDA FP16) and CPU fallback."""
        if not WHISPER_AVAILABLE:
            self.whisper_status = "failed"
            return
            
        self.whisper_status = "loading"

        def _load():
            try:
                import ctranslate2
                cuda_available = False
                try:
                    if ctranslate2.get_cuda_device_count() > 0:
                        cuda_available = True
                except Exception:
                    cuda_available = False

                if cuda_available:
                    print(f"[STT] GPU(CUDA FP16) 모드로 faster-whisper({self.whisper_model_name}) 모델 로딩 중...")
                    loaded_model = WhisperModel(
                        self.whisper_model_name,
                        device="cuda",
                        compute_type="float16"
                    )
                    # Warm-up inference to verify CUDA DLLs (cublas, cudnn, etc.)
                    dummy = np.zeros(16000, dtype=np.float32)
                    segments, _ = loaded_model.transcribe(dummy, beam_size=1)
                    list(segments)
                    
                    with self._whisper_lock:
                        self.whisper_model = loaded_model
                        self.whisper_device = "cuda"
                        self.whisper_compute_type = "float16"
                        self.whisper_status = "ready"
                    print(f"[STT] faster-whisper ({self.whisper_model_name}) [CUDA FP16] GPU 가속 로딩 및 검증 완료!")
                    return
            except Exception as e:
                print(f"[STT Warning] CUDA GPU 로딩 실패 (CPU int8 모드로 폴백 전환): {e}")

            # Fallback to CPU int8
            try:
                print(f"[STT] CPU(int8) 모드로 faster-whisper({self.whisper_model_name}) 로딩 중...")
                loaded_model = WhisperModel(
                    self.whisper_model_name,
                    device="cpu",
                    compute_type="int8"
                )
                with self._whisper_lock:
                    self.whisper_model = loaded_model
                    self.whisper_device = "cpu"
                    self.whisper_compute_type = "int8"
                    self.whisper_status = "ready"
                print(f"[STT] faster-whisper ({self.whisper_model_name}) [CPU int8] 로딩 완료!")
            except Exception as ex:
                print(f"[STT Error] faster-whisper CPU 로딩도 실패: {ex}")
                with self._whisper_lock:
                    self.whisper_status = "failed"

        threading.Thread(target=_load, daemon=True).start()

    def _get_model(self, model_name: str):
        """Retrieves or creates a GenerativeModel instance for given model name."""
        with self._config_lock:
            if not self.api_key:
                self.api_key = os.getenv("GEMINI_API_KEY")
                if self.api_key:
                    genai.configure(api_key=self.api_key)
                else:
                    raise ValueError("Gemini API Key가 설정되지 않았습니다.")
                    
            if model_name not in self._models:
                self._models[model_name] = genai.GenerativeModel(
                    model_name,
                    system_instruction=SYSTEM_INSTRUCTION
                )
            return self._models[model_name]

    def set_api_key(self, api_key: str):
        with self._config_lock:
            self.api_key = api_key
            try:
                genai.configure(api_key=api_key)
                self._models.clear()
                self._model_cooldowns.clear()
                print("[STT] Gemini API 키가 새로 설정되었습니다.")
            except Exception as e:
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
        """Transcribes and translates speech using Hybrid (Local Whisper + Gemini) or Cloud."""
        try:
            # Check Whisper Model Status
            if self.whisper_status == "loading":
                print("[STT] 로컬 Whisper 모델 로딩 대기 중... (음성 대기)")
                return ""
                
            with self._whisper_lock:
                whisper_model = self.whisper_model
                if whisper_model is not None:
                    try:
                        return self._transcribe_hybrid(wav_bytes, whisper_model)
                    except Exception as e:
                        print(f"[STT Hybrid Error] {e} -> Gemini Audio API로 폴백합니다.")

            # Fallback to Pure Gemini Audio API
            return self._transcribe_gemini_audio(wav_bytes)
        except Exception as e:
            print(f"[STT Error] 음성 변환 중 예외 발생: {e}")
            return ""

    def translate_text(self, text: str, detected_lang: str) -> str:
        """
        Translates foreign text into natural Korean with:
        1. Hallucination filter
        2. Fast LRU Memory Cache (0-token, 0ms)
        3. Multi-Model Failover Pool (bypasses 429 Quota Exceeded by switching models)
        """
        clean_text = text.strip()
        if not clean_text or is_hallucination(clean_text):
            return ""
            
        cache_key = f"{detected_lang}:{clean_text.lower()}"
        
        # 1. Check LRU Cache
        with self._cache_lock:
            if cache_key in self._translation_cache:
                self._translation_cache.move_to_end(cache_key)
                cached_res = self._translation_cache[cache_key]
                print(f"[Cache Hit] '{clean_text}' -> '{cached_res}' (0-token)")
                return cached_res
                
        prompt = f"다음 게임 보이스({detected_lang})를 한국어로 번역하라: \"{clean_text}\""
        gen_config = genai.types.GenerationConfig(
            temperature=0.0,
            max_output_tokens=150
        )

        now = time.time()
        # Filter available models (not in 429 cooldown)
        candidate_models = []
        for m_name in FLASH_MODEL_POOL:
            cooldown_until = self._model_cooldowns.get(m_name, 0)
            if now >= cooldown_until:
                candidate_models.append(m_name)
                
        # If all in cooldown, retry all
        if not candidate_models:
            candidate_models = FLASH_MODEL_POOL[:]

        for model_name in candidate_models:
            try:
                gemini = self._get_model(model_name)
                response = gemini.generate_content(
                    prompt,
                    generation_config=gen_config,
                    safety_settings=GAMING_SAFETY_SETTINGS
                )
                
                if response and hasattr(response, 'text') and response.text:
                    cleaned = response.text.strip().strip('"').strip("'")
                    if cleaned and not is_hallucination(cleaned):
                        # Store in LRU Cache
                        with self._cache_lock:
                            self._translation_cache[cache_key] = cleaned
                            if len(self._translation_cache) > 500:
                                self._translation_cache.popitem(last=False)
                        return cleaned
            except Exception as ex:
                err_str = str(ex)
                if "429" in err_str or "Quota exceeded" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    print(f"[Gemini 429 RateLimit] [{model_name}] 쿼터 초과 -> 다음 모델로 즉시 전환 (Failover)...")
                    # Set 45-second cooldown for this specific model
                    self._model_cooldowns[model_name] = time.time() + 45
                else:
                    print(f"[Gemini Error on {model_name}]: {ex}")

        return clean_text  # Fallback to original text if all models fail

    def _transcribe_hybrid(self, wav_bytes: bytes, whisper_model) -> str:
        mode, source_lang, target_lang = self.get_config()
        audio_stream = io.BytesIO(wav_bytes)
        
        # Whisper STT execution (Anti-Hallucination & Independent context config)
        segments, info = whisper_model.transcribe(
            audio_stream,
            beam_size=1,
            temperature=0.0,
            condition_on_previous_text=False,  # Prevents previous hallucination cascading
            no_speech_threshold=0.5,            # Filters background silence/noise
            compression_ratio_threshold=2.4,    # Filters repetitive word loops
            log_prob_threshold=-1.0,            # Filters low-confidence gibberish
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=300,
                speech_pad_ms=200
            )
        )
        
        # Filter high-quality speech segments
        valid_texts = []
        for segment in segments:
            # Skip noise or low-probability segments
            if segment.no_speech_prob > 0.6 or segment.avg_logprob < -1.2:
                continue
            text = segment.text.strip()
            if text and not is_hallucination(text):
                valid_texts.append(text)
            
        if not valid_texts:
            return ""
            
        stt_text = " ".join(valid_texts).strip()
        detected_lang = info.language
        
        if not stt_text or len(stt_text) < 2 or is_hallucination(stt_text):
            return ""
            
        print(f"[Whisper STT] 감지 언어: {detected_lang}, 텍스트: '{stt_text}'")
        
        # Local 0-token filtering
        if mode == "foreign_only":
            if detected_lang == "ko":
                print("[Filtering] 한국어 음성 감지됨 -> 자막 출력 제외 (0-token)")
                return ""
        elif mode == "specific":
            target_code = LANG_CODE_MAP.get(source_lang, "en")
            if detected_lang != target_code:
                print(f"[Filtering] 지정 언어({target_code})와 불일치({detected_lang}) -> 자막 출력 제외 (0-token)")
                return ""
        else:  # "all"
            if detected_lang == "ko":
                return stt_text

        # Fast Gemini Text Translation with Failover & Cache
        translated = self.translate_text(stt_text, detected_lang)
        if translated:
            print(f"[Translation] 번역 완료: '{translated}'")
        return translated

    def _transcribe_gemini_audio(self, wav_bytes: bytes) -> str:
        mode, source_lang, target_lang = self.get_config()
        audio_part = {
            "mime_type": "audio/wav",
            "data": wav_bytes
        }
        
        if mode == "foreign_only":
            rule_text = f"1. 음성이 {target_lang}인 경우 아무것도 출력하지 말 것.\n2. 외국어인 경우 {target_lang}(으)로 번역할 것."
        elif mode == "specific":
            rule_text = f"1. 음성이 '{source_lang}'인 경우만 {target_lang}(으)로 번역할 것.\n2. 그 외는 아무것도 출력하지 말 것."
        else:
            rule_text = f"1. {target_lang} 음성은 받아쓰기, 외국어는 {target_lang}(으)로 번역할 것."

        prompt = (
            "게임 보이스 자막 변환 엔진입니다. 오직 번역/받아쓰기 결과 텍스트만 출력하세요.\n"
            f"{rule_text}"
        )
        
        gen_config = genai.types.GenerationConfig(
            temperature=0.0,
            max_output_tokens=150
        )
        
        for model_name in FLASH_MODEL_POOL:
            try:
                gemini = self._get_model(model_name)
                response = gemini.generate_content(
                    [audio_part, prompt],
                    generation_config=gen_config,
                    safety_settings=GAMING_SAFETY_SETTINGS
                )
                if response and hasattr(response, 'text') and response.text:
                    res_text = response.text.strip()
                    if not is_hallucination(res_text):
                        return res_text
                return ""
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "Quota exceeded" in err_str:
                    self._model_cooldowns[model_name] = time.time() + 45
                    continue
                print(f"[Gemini Audio Error]: {e}")
                return ""
        return ""
