"""Qwen TTS provider implementation using local voice cloning."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import faulthandler
from urllib.request import Request, urlopen

from .base import TTSProvider


def _is_interactive() -> bool:
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except Exception:
        return False


def _prompt_yes_no(question: str, *, default_no: bool = True) -> bool:
    if not _is_interactive():
        return False

    suffix = "[y/N]" if default_no else "[Y/n]"
    while True:
        raw = input(f"{question} {suffix} ").strip().lower()
        if raw == "":
            return not default_no
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("Please answer y or n.")


def _parse_version_tuple(version_text: str) -> tuple[int, ...]:
    # Best-effort version parsing that works without external deps.
    nums = re.findall(r"\d+", version_text or "")
    return tuple(int(n) for n in nums) if nums else (0,)


def _get_installed_dist_version(dist_name: str) -> str | None:
    try:
        from importlib.metadata import version as dist_version

        return dist_version(dist_name)
    except Exception:
        return None


def _get_latest_pypi_version(package_name: str, *, timeout_s: float = 5.0) -> str | None:
    url = f"https://pypi.org/pypi/{package_name}/json"
    try:
        req = Request(url, headers={"User-Agent": "Tools-voiceover/1.0"})
        with urlopen(req, timeout=timeout_s) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return str(payload.get("info", {}).get("version") or "").strip() or None
    except Exception:
        return None


def _maybe_offer_pip_upgrade(dist_name: str, *, pip_name: str | None = None) -> None:
    pip_name = pip_name or dist_name

    installed = _get_installed_dist_version(dist_name)
    if not installed:
        return

    latest = _get_latest_pypi_version(pip_name)
    if not latest:
        return

    if _parse_version_tuple(latest) <= _parse_version_tuple(installed):
        return

    if not _prompt_yes_no(f"Update available for {pip_name}: {installed} → {latest}. Install now?"):
        return

    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "--disable-pip-version-check",
                pip_name,
            ],
            check=False,
        )
    except Exception as ex:
        print(f"Warning: failed to run pip upgrade for {pip_name}: {ex}")


def _looks_like_hf_repo_id(model_path: str) -> bool:
    # Heuristic: "org/name" with no drive letter, not an existing local path.
    if not model_path or "/" not in model_path:
        return False
    if re.match(r"^[a-zA-Z]:\\", model_path):
        return False
    if Path(model_path).exists():
        return False
    return True


def _maybe_offer_hf_model_update(repo_id: str) -> None:
    try:
        from huggingface_hub import model_info, snapshot_download
    except Exception:
        return

    try:
        local_path = snapshot_download(repo_id, local_files_only=True)
        local_snapshot = Path(local_path).name
    except Exception:
        # No local cache yet; let normal loading handle first download.
        return

    try:
        remote_sha = model_info(repo_id).sha
    except Exception:
        return

    if not remote_sha or remote_sha == local_snapshot:
        return

    if not _prompt_yes_no(
        f"A newer Qwen model snapshot is available for {repo_id}. Download/update cache now?"
    ):
        return

    try:
        snapshot_download(repo_id)
    except Exception as ex:
        print(f"Warning: failed to update model cache for {repo_id}: {ex}")


class QwenProvider(TTSProvider):
    """Qwen local TTS provider with voice cloning."""
    
    def __init__(self, config, log_func):
        super().__init__(config, log_func)
        self.model = None
        self.device = None
        self.voices_dir = None
        self.available_voices = {}
        self._amp_dtype = None
        self._want_flash_sdpa = False
    
    def initialize(self) -> None:
        """Initialize Qwen TTS model and scan available voices."""
        # Optional interactive update check (skip in non-interactive runs).
        if _is_interactive() and not os.environ.get("VOICEOVER_SKIP_UPDATES"):
            _maybe_offer_pip_upgrade("qwen-tts")

        try:
            import torch
            import soundfile as sf
            from qwen_tts import Qwen3TTSModel
            
            # Store imports as instance variables for later use
            self.torch = torch
            self.sf = sf
        except ImportError as e:
            raise ImportError(
                "Qwen TTS dependencies not installed. "
                "Install with: pip install torch soundfile qwen-tts"
            ) from e
        
        # Suppress transformers warnings
        import warnings
        import logging
        warnings.filterwarnings("ignore", message=".*pad_token_id.*")
        logging.getLogger("transformers.generation.utils").setLevel(logging.ERROR)
        
        # Get configuration
        model_path = getattr(self.config, "qwen_model_path", "Qwen/Qwen3-TTS-12Hz-0.6B-Base")
        self.voices_dir = Path(getattr(self.config, "qwen_voices_dir", ""))

        # Optional interactive model cache update (Hugging Face).
        if _is_interactive() and not os.environ.get("VOICEOVER_SKIP_UPDATES"):
            if isinstance(model_path, str) and _looks_like_hf_repo_id(model_path):
                _maybe_offer_hf_model_update(model_path)
        
        if not self.voices_dir or not self.voices_dir.exists():
            raise ValueError(
                f"Qwen voices directory not found or not configured: {self.voices_dir}. "
                f"Set 'qwen_voices_dir' in config.py"
            )
        
        # Set up device
        self.device = "cuda" if self.torch.cuda.is_available() else "cpu"
        
        # Performance knobs (safe defaults).
        if self.device == "cuda":
            try:
                # Allow TF32 for faster matmul/conv on Ampere+ (Ada included).
                if hasattr(self.torch.backends, "cuda") and hasattr(self.torch.backends.cuda, "matmul"):
                    self.torch.backends.cuda.matmul.allow_tf32 = True
                if hasattr(self.torch.backends, "cudnn"):
                    self.torch.backends.cudnn.allow_tf32 = True
                    self.torch.backends.cudnn.benchmark = True
                if hasattr(self.torch, "set_float32_matmul_precision"):
                    self.torch.set_float32_matmul_precision("high")
            except Exception:
                pass

        # Pick dtype. IMPORTANT: fp16 can be numerically unstable for this model on some
        # Windows/CUDA stacks and can lead to invalid sampling probabilities (and CUDA asserts).
        # Default to bf16 when supported; otherwise fall back to fp32 for stability.
        # Allow override via config.
        configured_dtype = str(getattr(self.config, "qwen_dtype", "") or "").strip().lower()
        if configured_dtype in {"fp16", "float16", "half"}:
            dtype = self.torch.float16
        elif configured_dtype in {"bf16", "bfloat16"}:
            dtype = self.torch.bfloat16
        elif configured_dtype in {"fp32", "float32"}:
            dtype = self.torch.float32
        else:
            if self.device == "cuda":
                try:
                    if hasattr(self.torch.cuda, "is_bf16_supported") and self.torch.cuda.is_bf16_supported():
                        dtype = self.torch.bfloat16
                    else:
                        dtype = self.torch.float32
                except Exception:
                    dtype = self.torch.float32
            else:
                dtype = self.torch.float32

        # Remember for autocast in generate_audio.
        self._amp_dtype = dtype

        if dtype == self.torch.bfloat16 and self.device == "cuda":
            # Some CUDA setups don’t support bf16; fall back gracefully.
            try:
                if hasattr(self.torch.cuda, "is_bf16_supported") and not self.torch.cuda.is_bf16_supported():
                    dtype = self.torch.float16
            except Exception:
                dtype = self.torch.float16

        # Prefer PyTorch's SDPA attention path when available.
        # This can use built-in CUDA kernels (Flash SDP / mem-efficient SDP) on modern GPUs
        # without needing the external flash-attn package.
        want_flash_sdpa = bool(getattr(self.config, "qwen_sdpa_flash", False))
        self._want_flash_sdpa = want_flash_sdpa
        try:
            if self.device == "cuda" and hasattr(self.torch.backends, "cuda"):
                cuda_backends = self.torch.backends.cuda
                if hasattr(cuda_backends, "enable_flash_sdp"):
                    cuda_backends.enable_flash_sdp(want_flash_sdpa)
                if hasattr(cuda_backends, "enable_mem_efficient_sdp"):
                    cuda_backends.enable_mem_efficient_sdp(True)
                if hasattr(cuda_backends, "enable_math_sdp"):
                    cuda_backends.enable_math_sdp(True)
        except Exception:
            pass
        
        print(f"Loading Qwen TTS model on {self.device}...")
        model_kwargs = {
            "device_map": self.device,
            "dtype": dtype,
            # Transformers supports this kwarg (forwarded into the underlying model config)
            # in many model classes. If qwen-tts ignores it, it is harmless.
            "attn_implementation": "sdpa",
        }
        try:
            self.model = Qwen3TTSModel.from_pretrained(model_path, **model_kwargs)
        except TypeError:
            # Older/newer qwen-tts may not accept forwarded kwargs.
            model_kwargs.pop("attn_implementation", None)
            self.model = Qwen3TTSModel.from_pretrained(model_path, **model_kwargs)
        print("Qwen TTS model loaded successfully")
        
        # Scan available voices
        self._scan_voices()
    
    def _scan_voices(self) -> None:
        """Scan voices directory and build mapping of game+character to voice folder."""
        self.available_voices = {}
        
        for voice_folder in self.voices_dir.iterdir():
            if not voice_folder.is_dir():
                continue
            
            voice_name = voice_folder.name
            ref_wav = voice_folder / "ref.wav"
            ref_txt = voice_folder / "ref.txt"
            
            if not (ref_wav.exists() and ref_txt.exists()):
                continue
            
            # Parse voice name: "GamePrefix_CharacterName"
            if "_" in voice_name:
                parts = voice_name.split("_", 1)
                game_prefix = parts[0]
                character_name = parts[1]
                
                key = (game_prefix, character_name)
                self.available_voices[key] = {
                    "folder": voice_folder,
                    "ref_wav": ref_wav,
                    "ref_txt": ref_txt,
                }
        
        print(f"Found {len(self.available_voices)} Qwen voice profiles")
    
    def get_supported_voices(self, game_name: str) -> list[str]:
        """Get list of available character voices for a game."""
        # Map game name to prefix used in voice folders
        game_prefix_map = {
            "BEngel": "BEngel",
            "Bound To College": "BtC",
            "GOS": "GOS",
        }
        
        game_prefix = game_prefix_map.get(game_name, game_name)
        
        voices = []
        for (prefix, character_name) in self.available_voices.keys():
            if prefix == game_prefix:
                voices.append(character_name)
        
        return sorted(voices)
    
    def generate_audio(
        self,
        text: str,
        game_name: str,
        character_name: str,
        output_path: Path,
        extra_context: dict | None = None,
    ) -> bool:
        """Generate audio using Qwen voice cloning."""
        extra_context = extra_context or {}
        
        # Map game name to prefix
        game_prefix_map = {
            "BEngel": "BEngel",
            "Bound To College": "BtC",
            "GOS": "GOS",
        }
        game_prefix = game_prefix_map.get(game_name, game_name)
        
        # Look up voice folder
        key = (game_prefix, character_name)
        voice_info = self.available_voices.get(key)
        
        if not voice_info:
            self.log(
                "skip",
                extra_context.get("identifier", ""),
                f"Qwen voice not found for '{game_prefix}_{character_name}'",
            )
            return False
        
        # Use target language from extra_context (e.g., 'french'), fallback to game's main language
        language = extra_context.get("target_language")
        if not language:
            game_dict = getattr(self.config, "game_dict", {})
            game_config = game_dict.get(game_name, {})
            language = game_config.get("main_lang", "English")

        # Prefer language-specific reference files if present in the voice folder.
        # Expected naming: ref_<suffix>.txt / ref_<suffix>.wav (e.g. ref_de.txt).
        def _normalize_ref_suffix(lang_value: str) -> str | None:
            raw = (lang_value or "").strip().lower()
            raw = raw.replace("_", "-")
            raw = re.sub(r"\s+", " ", raw)
            mapping = {
                "de": "de",
                "german": "de",
                "deutsch": "de",
                "fr": "fr",
                "french": "fr",
                "francais": "fr",
                "français": "fr",
                "es": "es",
                "spanish": "es",
                "spain": "es",
                "espanol": "es",
                "español": "es",
                "nl": "nl",
                "dutch": "nl",
                "netherlands": "nl",
                "pt": "ptpt",
                "pt-pt": "ptpt",
                "portuguese": "ptpt",
                "portugues": "ptpt",
                "português": "ptpt",
            }
            return mapping.get(raw)

        ref_wav_path = voice_info["ref_wav"]
        ref_txt_path = voice_info["ref_txt"]
        suffix = _normalize_ref_suffix(language)
        if suffix:
            voice_folder = Path(voice_info["folder"])
            candidate_wav = voice_folder / f"ref_{suffix}.wav"
            candidate_txt = voice_folder / f"ref_{suffix}.txt"
            if candidate_wav.exists() and candidate_txt.exists():
                ref_wav_path = candidate_wav
                ref_txt_path = candidate_txt

        # Load reference transcript (matching selected ref_txt_path)
        try:
            with open(ref_txt_path, "r", encoding="utf-8") as f:
                ref_transcript = f.read().strip()
        except Exception as ex:
            self.log(
                "error",
                extra_context.get("identifier", ""),
                f"Failed to read reference transcript '{ref_txt_path.name}': {ex}",
            )
            return False
        
        # Map Ren'Py folder names to Qwen language codes (lowercase English names)
        # Qwen supports: 'auto', 'chinese', 'english', 'french', 'german', 'italian', 
        #                'japanese', 'korean', 'portuguese', 'russian', 'spanish'
        lang_map = {
            "english": "english",
            "french": "french",
            "francais": "french",
            "français": "french",
            "german": "german",
            "deutsch": "german",
            "spanish": "spanish",
            "espanol": "spanish",
            "español": "spanish",
            "italian": "italian",
            "italiano": "italian",
            "portuguese": "portuguese",
            "portugues": "portuguese",
            "português": "portuguese",
            "russian": "russian",
            "russian_old": "russian",
            "japanese": "japanese",
            "korean": "korean",
            "chinese": "chinese",
        }
        language_lower = language.lower()
        language = lang_map.get(language_lower, language_lower)
        
        # Optional override to force a specific Qwen language (e.g. "german").
        forced_lang = str(getattr(self.config, "qwen_force_language", "") or "").strip().lower()
        if forced_lang:
            language = forced_lang
        else:
            # Use 'auto' for non-English to let Qwen detect from text
            # (voice characteristics will still come from English ref audio)
            if language != "english":
                language = "auto"
        
        # Show what's being generated
        identifier = extra_context.get("identifier", "")
        print(f"  Generating [{identifier}] in {language}: {text[:80]}{'...' if len(text) > 80 else ''}")

        # Optional per-line input logging to diagnose hangs.
        if bool(getattr(self.config, "qwen_log_inputs", False)):
            text_clean = " ".join(str(text).split())
            excerpt = text_clean[:200] + ("..." if len(text_clean) > 200 else "")
            char_count = len(text_clean)
            word_count = len(text_clean.split()) if text_clean else 0
            voice_label = f"{game_prefix}_{character_name}"
            self.log(
                "input",
                identifier,
                f"chars={char_count} words={word_count} lang={language} voice={voice_label} text={excerpt}",
            )
        
        # Generate audio
        try:
            debug_timing = bool(getattr(self.config, "qwen_debug_timing", False))
            log_timing = bool(getattr(self.config, "qwen_log_timing", False)) or debug_timing
            t_start = time.perf_counter()
            hang_dump_seconds = float(getattr(self.config, "qwen_hang_dump_seconds", 0) or 0)
            hang_dump_enabled = hang_dump_seconds > 0
            hang_dump_handle = None
            if hang_dump_enabled:
                # Dump Python stack traces if a single line takes too long.
                hang_log_path = str(getattr(self.config, "voiceover_log_path", "") or "").strip()
                if hang_log_path:
                    try:
                        hang_dump_handle = open(hang_log_path, "a", encoding="utf-8", newline="")
                        faulthandler.dump_traceback_later(
                            hang_dump_seconds,
                            repeat=False,
                            file=hang_dump_handle,
                        )
                    except Exception:
                        hang_dump_handle = None
                        faulthandler.dump_traceback_later(hang_dump_seconds, repeat=False)
                else:
                    faulthandler.dump_traceback_later(hang_dump_seconds, repeat=False)

            # IMPORTANT: Do NOT force Torch's flash SDPA kernel here.
            # On some Windows/CUDA combinations it can trigger a device-side assert,
            # which then makes every subsequent generation fail until the process restarts.
            # We keep mem-efficient + math enabled (stable) and fall back to math-only.
            def _run_generate(*, mem_efficient: bool):
                cuda_backends = getattr(self.torch.backends, "cuda", None)
                sdp_ctx = None
                if self.device == "cuda":
                    # Prefer the newer API if present; fall back for older torch builds.
                    try:
                        if hasattr(self.torch, "nn") and hasattr(self.torch.nn, "attention") and hasattr(
                            self.torch.nn.attention, "sdpa_kernel"
                        ):
                            sdp_ctx = self.torch.nn.attention.sdpa_kernel(
                                enable_flash=self._want_flash_sdpa,
                                enable_mem_efficient=mem_efficient,
                                enable_math=True,
                            )
                        elif cuda_backends is not None and hasattr(cuda_backends, "sdp_kernel"):
                            sdp_ctx = cuda_backends.sdp_kernel(
                                enable_flash=self._want_flash_sdpa,
                                enable_mem_efficient=mem_efficient,
                                enable_math=True,
                            )
                    except Exception:
                        sdp_ctx = None

                inference_ctx = self.torch.inference_mode() if hasattr(self.torch, "inference_mode") else None

                autocast_ctx = None
                try:
                    if (
                        self.device == "cuda"
                        and hasattr(self.torch, "autocast")
                        and self._amp_dtype in {self.torch.float16, self.torch.bfloat16}
                    ):
                        autocast_ctx = self.torch.autocast(device_type="cuda", dtype=self._amp_dtype)
                except Exception:
                    autocast_ctx = None

                # Enter contexts (manually, to keep compatibility across torch versions)
                entered = []
                for ctx in (sdp_ctx, inference_ctx, autocast_ctx):
                    if ctx is None:
                        continue
                    entered.append(ctx)
                    ctx.__enter__()
                try:
                    # Calculate max_new_tokens based on text length
                    # Rule of thumb: ~10-15 tokens per character for TTS @ 12Hz
                    # Add buffer for safety, cap at reasonable maximum
                    base_max = getattr(self.config, "qwen_max_new_tokens", None)
                    if base_max is None:
                        # Dynamic: 12 tokens/char + 50% buffer, min 256, max 4096
                        estimated = len(text) * 12
                        max_tokens = min(max(int(estimated * 1.5), 256), 4096)
                    else:
                        max_tokens = base_max
                    
                    # Log max_tokens if debug enabled
                    if debug_timing:
                        id_str = extra_context.get("identifier", "")
                        if id_str:
                            print(f"  max_tokens={max_tokens} for {len(text)} chars")
                    
                    # Get x_vector_only_mode from config (prevents ref text from being spoken)
                    x_vector_only = getattr(self.config, "qwen_x_vector_only", False)
                    
                    return self.model.generate_voice_clone(
                        text=text,
                        language=language,
                        ref_audio=str(ref_wav_path),
                        ref_text=ref_transcript,
                        x_vector_only_mode=x_vector_only,
                        max_new_tokens=max_tokens,
                    )
                finally:
                    for ctx in reversed(entered):
                        try:
                            ctx.__exit__(None, None, None)
                        except Exception:
                            pass

            try:
                wavs, sr = _run_generate(mem_efficient=True)
            except Exception:
                wavs, sr = _run_generate(mem_efficient=False)
            finally:
                if hang_dump_enabled:
                    try:
                        faulthandler.cancel_dump_traceback_later()
                    except Exception:
                        pass
                    if hang_dump_handle is not None:
                        try:
                            hang_dump_handle.close()
                        except Exception:
                            pass

            if debug_timing:
                t_gen = time.perf_counter() - t_start
                print(f"  Timing [{identifier}] generate: {t_gen:.2f}s")
            if log_timing:
                t_gen = time.perf_counter() - t_start
                self.log("timing", identifier, f"generate_s={t_gen:.2f}")
            
            # Save as temporary WAV first (specify format explicitly)
            temp_wav = output_path.with_suffix('.wav.tmp')
            if temp_wav.exists():
                try:
                    temp_wav.unlink()
                except Exception:
                    pass
            self.sf.write(str(temp_wav), wavs[0], sr, format='WAV')

            if debug_timing:
                t_write = time.perf_counter() - t_start
                print(f"  Timing [{identifier}] wav write: {t_write:.2f}s")
            if log_timing:
                t_write = time.perf_counter() - t_start
                self.log("timing", identifier, f"wav_write_s={t_write:.2f}")
            
            if not temp_wav.exists():
                raise RuntimeError("Audio generation completed but temp WAV file is missing")

            # Get output format from config (default: mp3)
            output_format = str(getattr(self.config, "qwen_output_format", "mp3") or "mp3").strip().lower()
            
            # Fast path: keep WAV if requested
            if output_format in {"wav", "wave"}:
                wav_target = output_path if output_path.suffix.lower() == ".wav" else output_path.with_suffix(".wav")
                try:
                    os.replace(str(temp_wav), str(wav_target))
                except Exception:
                    temp_wav.rename(wav_target)
                if debug_timing:
                    t_done = time.perf_counter() - t_start
                    print(f"  Timing [{identifier}] done (wav): {t_done:.2f}s")
                if log_timing:
                    t_done = time.perf_counter() - t_start
                    self.log("timing", identifier, f"total_s={t_done:.2f} format=wav")
                return True
            
            # Convert WAV to MP3 or OGG
            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_wav(str(temp_wav))
                
                if output_format == "mp3":
                    audio.export(str(output_path), format="mp3", bitrate="128k")
                elif output_format == "ogg":
                    audio.export(str(output_path), format="ogg", codec="libvorbis", parameters=["-q:a", "4"])
                else:
                    # Fallback to mp3
                    audio.export(str(output_path), format="mp3", bitrate="128k")
                
                temp_wav.unlink()  # Delete temp WAV file
                if debug_timing:
                    t_done = time.perf_counter() - t_start
                    print(f"  Timing [{identifier}] done ({output_format}): {t_done:.2f}s")
                if log_timing:
                    t_done = time.perf_counter() - t_start
                    self.log("timing", identifier, f"total_s={t_done:.2f} format={output_format}")
            except ImportError:
                # If pydub not available, just rename WAV to output (fallback)
                temp_wav.rename(output_path)
                print(f"Warning: pydub not installed, saving as WAV. Install with: pip install pydub")
                if debug_timing:
                    t_done = time.perf_counter() - t_start
                    print(f"  Timing [{identifier}] done (wav fallback): {t_done:.2f}s")
                if log_timing:
                    t_done = time.perf_counter() - t_start
                    self.log("timing", identifier, f"total_s={t_done:.2f} format=wav_fallback")
            
            if not output_path.exists():
                raise RuntimeError("Audio conversion completed but output file is missing")
            
            # Removed the print statement here - gen.py handles progress display
            return True
            
        except Exception as ex:
            self.log(
                "error",
                extra_context.get("identifier", ""),
                f"Qwen TTS failed: {type(ex).__name__}: {ex}",
            )
            return False
    
    def get_file_extension(self) -> str:
        """Return output extension based on config."""
        output_format = str(getattr(self.config, "qwen_output_format", "mp3") or "mp3").strip().lower()
        if output_format in {"wav", "wave"}:
            return ".wav"
        elif output_format == "ogg":
            return ".ogg"
        return ".mp3"  # Default to mp3
    
    def cleanup(self) -> None:
        """Clean up model resources."""
        if self.model is not None:
            # Free up CUDA memory if applicable
            if self.device == "cuda" and hasattr(self.torch.cuda, "empty_cache"):
                self.torch.cuda.empty_cache()
        self.model = None
