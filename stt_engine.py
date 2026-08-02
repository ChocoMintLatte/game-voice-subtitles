import google.generativeai as genai
import os
import io
import threading
from dotenv import load_dotenv

# Load env variables
load_dotenv()

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
            
        self.model_name = "gemini-3.1-flash-lite"
        self._gemini_model = None
        
        # Thread locks to prevent GUI freezing
        self._config_lock = threading.Lock()
        self._whisper_lock = threading.Lock()
        
        # Translation configuration
        self.mode = os.getenv("TRANSLATION_MODE", "foreign_only")  # "all", "foreign_only", "specific"
        self.source_lang = os.getenv("SOURCE_LANG", "일본어")
        self.target_lang = os.getenv("TARGET_LANG", "한국어")
        
        # Whisper model setup
        self.whisper_model_name = whisper_model_name
        self.whisper_model = None
        self.whisper_device = "cuda"
        self.whisper_compute_type = "float16"
        self.init_whisper()
        
    def init_whisper(self):
        if not WHISPER_AVAILABLE:
            return
            
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
                    device = "cuda"
                    compute_type = "float16"
                    print(f"[STT] GPU(CUDA FP16) 모드로 faster-whisper({self.whisper_model_name}) 모델을 로딩합니다...")
                else:
                    device = "cpu"
                    compute_type = "int8"
                    print("[STT] CUDA를 사용할 수 없어 CPU(int8) 모드로 백그라운드 초기화합니다.")

                loaded_model = WhisperModel(
                    self.whisper_model_name,
                    device=device,
                    compute_type=compute_type
                )
                
                with self._whisper_lock:
                    self.whisper_model = loaded_model
                    self.whisper_device = device
                    self.whisper_compute_type = compute_type
                    
                print(f"[STT] faster-whisper ({self.whisper_model_name}) [{device.upper()}] 모델 로딩 완료!")
            except Exception as e:
                print(f"[STT Error] GPU 로딩 실패 (CPU fallback 시도 중...): {e}")
                try:
                    loaded_model = WhisperModel(
                        self.whisper_model_name,
                        device="cpu",
                        compute_type="int8"
                    )
                    with self._whisper_lock:
                        self.whisper_model = loaded_model
                        self.whisper_device = "cpu"
                        self.whisper_compute_type = "int8"
                    print(f"[STT] faster-whisper CPU 모드로 로딩 성공!")
                except Exception as ex:
                    print(f"[STT Error] faster-whisper CPU 로딩도 실패: {ex}")

        threading.Thread(target=_load, daemon=True).start()

    @property
    def model(self):
        with self._config_lock:
            if self._gemini_model is None:
                if not self.api_key:
                    self.api_key = os.getenv("GEMINI_API_KEY")
                    if self.api_key:
                        genai.configure(api_key=self.api_key)
                    else:
                        raise ValueError("Gemini API Key가 설정되지 않았습니다.")
                self._gemini_model = genai.GenerativeModel(self.model_name)
            return self._gemini_model

    def set_api_key(self, api_key):
        with self._config_lock:
            self.api_key = api_key
            try:
                genai.configure(api_key=api_key)
                self._gemini_model = genai.GenerativeModel(self.model_name)
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

    def transcribe(self, wav_bytes):
        try:
            with self._whisper_lock:
                current_whisper = self.whisper_model
                
            if current_whisper is not None:
                return self._transcribe_hybrid(wav_bytes, current_whisper)
            else:
                return self._transcribe_gemini_audio(wav_bytes)
        except Exception as e:
            print(f"[STT Error] 변환 실패: {e}")
            return f"[에러: {str(e)}]"

    def _transcribe_hybrid(self, wav_bytes, whisper_model):
        mode, source_lang, target_lang = self.get_config()
        audio_stream = io.BytesIO(wav_bytes)
        
        # Whisper STT execution
        segments, info = whisper_model.transcribe(
            audio_stream,
            beam_size=1,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=300)
        )
        segments = list(segments)
            
        if not segments:
            return ""
            
        stt_text = "".join(segment.text for segment in segments).strip()
        detected_lang = info.language
        
        if not stt_text or len(stt_text) < 2:
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

        # Fast Gemini Text Translation
        prompt = (
            f"너는 에이펙스 레전드 / 발로란트 게임 보이스 채팅 오버레이 번역기야.\n"
            f"다음 게임 보이스 텍스트({detected_lang})를 자연스러운 한국어로 번역해줘.\n\n"
            f"규칙:\n"
            f"1. 인사말, 주석, 부연설명 없이 **오직 번역된 결과물만** 출력할 것.\n"
            f"2. Ult(궁), Low(피없음), Push(지르자), Flank(돌다) 등 게임 용어 문맥을 살려 자연스럽게 번역할 것.\n"
            f"3. 텍스트: \"{stt_text}\""
        )

        gen_config = genai.types.GenerationConfig(
            temperature=0.0,
            max_output_tokens=100
        )

        try:
            gemini = self.model
            response = gemini.generate_content(prompt, generation_config=gen_config)
            
            if (response and response.candidates and 
                response.candidates[0].content and 
                response.candidates[0].content.parts):
                return response.text.strip()
            return stt_text
        except Exception as ex:
            print(f"[Gemini Translation Error]: {ex}")
            return stt_text

    def _transcribe_gemini_audio(self, wav_bytes):
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
            max_output_tokens=100
        )
        
        try:
            gemini = self.model
            response = gemini.generate_content([audio_part, prompt], generation_config=gen_config)
            return response.text.strip() if response and hasattr(response, 'text') else ""
        except Exception as e:
            print(f"[Gemini Audio Error]: {e}")
            return f"[에러: {str(e)}]"
