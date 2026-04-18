import base64
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization


def _b64e(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _b64d(s: str) -> bytes:
    return base64.b64decode(s)


@dataclass
class NodeSession:
    node_id: str
    session_key: bytes  # 32-byte key derived from ECDH, used to wrap the match key


class CryptoManager:
    """
    Key hierarchy:
      node session key  — derived per-node via X25519 ECDH + HKDF at registration
      match key         — random AES-256 key per match, encrypted with each node's session key
      prompt ciphertext — AES-256-GCM with match key, unique 12-byte nonce per prompt
    """

    def __init__(self):
        self._sessions: dict[str, NodeSession] = {}
        self._match_keys: dict[str, bytes] = {}

    # ── registration handshake ────────────────────────────────────────────────

    def establish_session(self, node_id: str, node_pubkey_b64: str) -> str:
        """
        ECDH with node's ephemeral X25519 public key.
        Stores derived session key; returns server's ephemeral public key (b64)
        to include in REGISTER_OK so the node can derive the same shared secret.
        """
        if node_id in self._sessions:
            del self._sessions[node_id]
        node_pubkey = X25519PublicKey.from_public_bytes(_b64d(node_pubkey_b64))
        server_private = X25519PrivateKey.generate()
        shared_secret = server_private.exchange(node_pubkey)

        session_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"agentic-juggling-session-v1",
        ).derive(shared_secret)

        self._sessions[node_id] = NodeSession(node_id=node_id, session_key=session_key)

        server_pubkey_bytes = server_private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return _b64e(server_pubkey_bytes)

    def has_session(self, node_id: str) -> bool:
        return node_id in self._sessions

    # ── match key lifecycle ───────────────────────────────────────────────────

    def generate_match_key(self, match_id: str) -> None:
        if match_id in self._match_keys:
            raise ValueError(f"match key already exists for {match_id!r}")
        self._match_keys[match_id] = os.urandom(32)

    def encrypt_match_key_for_node(self, match_id: str, node_id: str) -> str:
        """
        Wrap the match AES key with the node's session key (AES-256-GCM).
        Returns b64(nonce || ciphertext) — included in the START packet so the
        node can unwrap it and then decrypt the prompt schedule.
        """
        if match_id not in self._match_keys:
            raise ValueError(f"no match key for {match_id!r}")
        if node_id not in self._sessions:
            raise ValueError(f"no session for node {node_id!r}")
        match_key = self._match_keys[match_id]
        session_key = self._sessions[node_id].session_key
        nonce = os.urandom(12)
        ciphertext = AESGCM(session_key).encrypt(nonce, match_key, None)
        return _b64e(nonce + ciphertext)

    def revoke_match_key(self, match_id: str) -> None:
        self._match_keys.pop(match_id, None)

    # ── prompt encryption ─────────────────────────────────────────────────────

    def encrypt_prompt(self, match_id: str, prompt: str) -> str:
        """
        Encrypt a single prompt with the match key.
        Returns b64(nonce || ciphertext). Each prompt gets a fresh nonce.
        match_id is bound as AAD so ciphertexts cannot be replayed across matches.
        """
        if match_id not in self._match_keys:
            raise ValueError(f"no match key for {match_id!r}")
        match_key = self._match_keys[match_id]
        nonce = os.urandom(12)
        ciphertext = AESGCM(match_key).encrypt(nonce, prompt.encode(), match_id.encode())
        return _b64e(nonce + ciphertext)

    def encrypt_schedule(self, match_id: str, schedule: list[dict]) -> list[dict]:
        """
        Encrypt all prompts in a schedule in-place (returns new list).
        Input:  [{"delay": float, "prompt": str}, ...]
        Output: [{"delay": float, "encrypted_prompt": str}, ...]
        """
        return [
            {"delay": entry["delay"], "encrypted_prompt": self.encrypt_prompt(match_id, entry["prompt"])}
            for entry in schedule
        ]
