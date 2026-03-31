"""TTS Provider implementations for voice generation."""

from .base import TTSProvider


def get_provider(provider_name: str, config, log_func) -> TTSProvider:
    """Factory function to create the appropriate TTS provider.
    
    Args:
        provider_name: Name of the provider ("elevenlabs" or "qwen")
        config: Configuration module
        log_func: Logging function
    
    Returns:
        TTSProvider instance
    
    Raises:
        ValueError: If provider_name is not recognized
    """
    provider_name = provider_name.lower().strip()
    
    if provider_name == "elevenlabs":
        from .elevenlabs_provider import ElevenLabsProvider

        return ElevenLabsProvider(config, log_func)
    elif provider_name == "qwen":
        from .qwen_provider import QwenProvider

        return QwenProvider(config, log_func)
    else:
        raise ValueError(
            f"Unknown TTS provider: '{provider_name}'. "
            f"Available providers: 'elevenlabs', 'qwen'"
        )


__all__ = ["TTSProvider", "get_provider"]
