"""ElevenLabs TTS provider implementation."""

import re
from pathlib import Path

from elevenlabs import ElevenLabs, save

from .base import TTSProvider


MODEL_V3 = "eleven_v3"
MODEL_MARVIN_V2_5 = "eleven_turbo_v2_5"

_TOKEN_RE = re.compile(r"\S+")


class ElevenLabsProvider(TTSProvider):
    """ElevenLabs TTS provider."""
    
    def __init__(self, config, log_func):
        super().__init__(config, log_func)
        self.client = None
        self.voice_name_to_id = {}
    
    def initialize(self) -> None:
        """Initialize ElevenLabs client and cache voice list."""
        if not getattr(self.config, "api_key", ""):
            raise ValueError(
                "ElevenLabs API key not configured. "
                "Set environment variable ELEVENLABS_API_KEY and re-run."
            )
        
        self.client = ElevenLabs(api_key=self.config.api_key)
        
        print("Caching ElevenLabs voices...")
        self.voice_name_to_id = {
            voice.name: voice.voice_id
            for voice in self.client.voices.get_all().voices
        }
    
    def get_supported_voices(self, game_name: str) -> list[str]:
        """Get list of available voice names for a game from ElevenLabs."""
        if not self.voice_name_to_id:
            return []
        
        # Extract character names from voice names matching "GameName: CharacterName"
        prefix = f"{game_name}: "
        voices = []
        for voice_name in self.voice_name_to_id.keys():
            if voice_name.startswith(prefix):
                character_name = voice_name[len(prefix):]
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
        """Generate audio using ElevenLabs TTS."""
        extra_context = extra_context or {}
        
        # Build ElevenLabs voice name
        voice_name = f"{game_name}: {character_name}"
        voice_id = self.voice_name_to_id.get(voice_name)
        
        if not voice_id:
            self.log(
                "skip",
                extra_context.get("identifier", ""),
                f"unknown voice '{voice_name}'",
            )
            return False
        
        # Determine model and build final text
        is_marvin = character_name.strip().lower() == "marvin"
        model_id = MODEL_MARVIN_V2_5 if is_marvin else MODEL_V3
        
        final_text = text
        if model_id == MODEL_V3:
            # Extract emotion from Ren'Py script for v3 model
            emotion = self._extract_side_image_emotion(
                extra_context.get("renpy_script"),
                extra_context.get("character_code"),
            )
            if emotion:
                final_text = f"[{emotion}] {text}"
        
        # Generate audio
        try:
            audio = self.client.text_to_speech.convert(
                voice_id,
                text=final_text,
                model_id=model_id,
            )
            save(audio, str(output_path))
            
            if not output_path.exists():
                raise RuntimeError("save() completed but output file is missing")
            
            print(f"{output_path}, {voice_name}, model={model_id}")
            return True
            
        except Exception as ex:
            self.log(
                "error",
                extra_context.get("identifier", ""),
                f"tts/save failed: {type(ex).__name__}: {ex}",
            )
            return False
    
    def get_file_extension(self) -> str:
        """ElevenLabs outputs MP3 files."""
        return ".mp3"
    
    def _extract_side_image_emotion(
        self,
        renpy_script: str | None,
        character_code: str | None,
    ) -> str | None:
        """Extract emotion tag from Ren'Py script for emotion-aware TTS.
        
        This looks for patterns like: 'c "happy" "[what]"' where 'c' is the character
        code and "happy" is the emotion.
        """
        if not renpy_script or not character_code:
            return None
        
        text = renpy_script.strip()
        if not text or "[what]" not in text:
            return None
        
        text = text.lstrip('"\'')
        tokens = _TOKEN_RE.findall(text)
        if len(tokens) < 2:
            return None
        
        if tokens[0] != character_code:
            return None
        
        emotion = tokens[1].strip('"\'')
        if not emotion or "[what]" in emotion:
            return None
        
        # Clean and normalize emotion
        emotion = emotion.lower().strip().replace("_", " ")
        emotion = re.sub(r"[^a-z\s-]", "", emotion)
        emotion = re.sub(r"\s+", " ", emotion).strip()
        return emotion or None
