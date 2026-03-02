from clausy.providers import ProviderRegistry
from clausy.providers.gemini_web import GeminiWebProvider


def test_default_registry_includes_gemini_web_provider():
    registry = ProviderRegistry.default(chatgpt_url="https://chatgpt.com")

    provider = registry.get("gemini_web")

    assert isinstance(provider, GeminiWebProvider)
    assert provider.url == "https://gemini.google.com"
