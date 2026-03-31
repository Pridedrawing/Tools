"""Abstract base class for TTS providers."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class TTSProvider(ABC):
    """Abstract base class for text-to-speech providers."""
    
    def __init__(self, config: Any, log_func: callable):
        """Initialize the provider.
        
        Args:
            config: Configuration module containing settings
            log_func: Function to log events (signature: event, identifier, detail)
        """
        self.config = config
        self.log = log_func
    
    @abstractmethod
    def initialize(self) -> None:
        """Initialize the provider (load models, connect to API, etc.).
        
        Raises:
            Exception: If initialization fails
        """
        pass
    
    @abstractmethod
    def get_supported_voices(self, game_name: str) -> list[str]:
        """Get list of available voice names for a game.
        
        Args:
            game_name: Name of the game
        
        Returns:
            List of voice names (e.g., ["Ben", "Chris", "Narrator"])
        """
        pass
    
    @abstractmethod
    def generate_audio(
        self,
        text: str,
        game_name: str,
        character_name: str,
        output_path: Path,
        extra_context: dict | None = None,
    ) -> bool:
        """Generate audio for the given text and save to output path.
        
        Args:
            text: Text to synthesize
            game_name: Name of the game (e.g., "BEngel")
            character_name: Name of the character (e.g., "Ben")
            output_path: Path where audio file should be saved
            extra_context: Optional dict with additional context:
                - "character_code": Original character code from CSV
                - "renpy_script": Ren'Py script line for emotion extraction
                - "identifier": Audio file identifier
        
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def get_file_extension(self) -> str:
        """Get the audio file extension this provider outputs.
        
        Returns:
            File extension with dot (e.g., ".mp3", ".wav")
        """
        pass
    
    def cleanup(self) -> None:
        """Clean up resources (optional, override if needed)."""
        pass
