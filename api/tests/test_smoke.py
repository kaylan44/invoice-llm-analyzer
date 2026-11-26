"""Smoke tests: the package and the Gemini SDK import inside the workspace environment."""


def test_invoice_api_imports() -> None:
    import invoice_api

    assert invoice_api.__name__ == "invoice_api"


def test_gemini_sdk_imports() -> None:
    from google import genai

    assert hasattr(genai, "Client")
