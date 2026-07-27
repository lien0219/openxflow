import base64
import json

import pytest
from langflow.channels.security.wecom_ai_crypto import WeComAIBotCrypt, WeComAIBotCryptoError

_TOKEN = "callback-token"
_KEY = base64.b64encode(bytes(range(32))).decode().rstrip("=")


def test_wecom_ai_json_crypto_roundtrip() -> None:
    crypt = WeComAIBotCrypt(_TOKEN, _KEY)
    response = crypt.encrypt_response(
        {"msgtype": "text", "text": {"content": "你好"}},
        timestamp="1710000000",
        nonce="nonce",
        random_prefix=b"0123456789abcdef",
    )
    envelope = json.loads(response)

    decoded = crypt.decrypt_payload(
        response.encode(),
        signature=envelope["msgsignature"],
        timestamp=envelope["timestamp"],
        nonce=envelope["nonce"],
    )

    assert decoded == {"msgtype": "text", "text": {"content": "你好"}}


def test_wecom_ai_url_verification_roundtrip() -> None:
    crypt = WeComAIBotCrypt(_TOKEN, _KEY)
    response = json.loads(
        crypt.encrypt_response(
            {"challenge": "verified"},
            timestamp="1710000000",
            nonce="nonce",
            random_prefix=b"0123456789abcdef",
        )
    )

    plaintext = crypt.verify_url(
        signature=response["msgsignature"],
        timestamp=response["timestamp"],
        nonce=response["nonce"],
        echo=response["encrypt"],
    )

    assert json.loads(plaintext) == {"challenge": "verified"}


def test_wecom_ai_crypto_rejects_invalid_signature() -> None:
    crypt = WeComAIBotCrypt(_TOKEN, _KEY)
    envelope = json.loads(
        crypt.encrypt_response(
            {"msgtype": "text", "text": {"content": "hello"}},
            timestamp="1710000000",
            nonce="nonce",
            random_prefix=b"0123456789abcdef",
        )
    )

    with pytest.raises(WeComAIBotCryptoError, match="signature"):
        crypt.decrypt_payload(
            json.dumps(envelope).encode(),
            signature="invalid",
            timestamp=envelope["timestamp"],
            nonce=envelope["nonce"],
        )
