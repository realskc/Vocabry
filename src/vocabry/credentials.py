from __future__ import annotations

import keyring

SERVICE_NAME = "Vocabry"
DEEPSEEK_ACCOUNT = "deepseek-api-key"


def get_deepseek_key() -> str | None:
    return keyring.get_password(SERVICE_NAME, DEEPSEEK_ACCOUNT)


def set_deepseek_key(value: str) -> None:
    keyring.set_password(SERVICE_NAME, DEEPSEEK_ACCOUNT, value)


def delete_deepseek_key() -> None:
    try:
        keyring.delete_password(SERVICE_NAME, DEEPSEEK_ACCOUNT)
    except keyring.errors.PasswordDeleteError:
        pass
