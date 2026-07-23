import pytest
from langflow.channels.domain.exceptions import ChannelBindingCodeInvalidError
from langflow.channels.services.binding import generate_binding_code, hash_binding_code, normalize_binding_code


def test_generated_binding_code_uses_safe_alphabet() -> None:
    code = generate_binding_code()
    assert len(code) == 8
    assert "0" not in code
    assert "1" not in code
    assert "I" not in code
    assert "O" not in code


def test_binding_code_normalization_is_case_and_space_insensitive() -> None:
    assert normalize_binding_code("ab cd 2345") == "ABCD2345"
    assert hash_binding_code("ab cd 2345") == hash_binding_code("ABCD2345")


def test_invalid_binding_code_is_rejected() -> None:
    with pytest.raises(ChannelBindingCodeInvalidError):
        normalize_binding_code("INVALID!")
