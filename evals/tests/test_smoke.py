"""Smoke test: evals can import the api package through the uv workspace."""


def test_evals_sees_api_package() -> None:
    import invoice_api
    import invoice_evals

    assert invoice_evals.__name__ == "invoice_evals"
    assert invoice_api.__name__ == "invoice_api"
