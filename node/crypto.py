import base64
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization


def _b64e(data: bytes) -> str:
    return base64.b64encode(data).decode()

def _b64d(s: str) -> bytes:
    return base64.b64decode(s)


class NodeCrypto:
    """
    Node-side mirror of server's CryptoManager.
    Key flow: ECDH at registration → session key → unwrap match key → decrypt prompts.
    """

    def __init__(self):
        self._private_key = X25519PrivateKey.generate()
        self._session_key: bytes | None = None
        self._match_keys: dict[str, bytes] = {}

    def pubkey_b64(self) -> str:
        raw = self._private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return _b64e(raw)

    def derive_session_key(self, server_pubkey_b64: str) -> None:
        server_pubkey = X25519PublicKey.from_public_bytes(_b64d(server_pubkey_b64))
        shared_secret = self._private_key.exchange(server_pubkey)
        self._session_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"agentic-juggling-session-v1",
        ).derive(shared_secret)

    def unwrap_match_key(self, match_id: str, encrypted_match_key_b64: str) -> None:
        blob = _b64d(encrypted_match_key_b64)
        nonce, ciphertext = blob[:12], blob[12:]
        self._match_keys[match_id] = AESGCM(self._session_key).decrypt(nonce, ciphertext, None)

    def decrypt_prompt(self, match_id: str, encrypted_prompt_b64: str) -> str:
        if match_id not in self._match_keys:
            raise ValueError(f"no match key for {match_id!r}")
        blob = _b64d(encrypted_prompt_b64)
        nonce, ciphertext = blob[:12], blob[12:]
        return AESGCM(self._match_keys[match_id]).decrypt(nonce, ciphertext, match_id.encode()).decode()

    def revoke_match_key(self, match_id: str) -> None:
        self._match_keys.pop(match_id, None)
