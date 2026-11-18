import os
import jwt
import random, string


def _secret():
    return os.getenv("ORDERS_SECRET")


def generate_new_token(role: str = "default", owner: str = ""):
    """
    Генерирует новый токен с заданной ролью
    """
    secret = _secret()
    payload = {
        "salt": "".join(random.choices(string.ascii_letters + string.digits + '-@%', k=32)),
        "role": role,
        "owner": owner
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def read_payload(token: str) -> dict | None:
    """
    Читает токен и возвращает payload
    """
    try:
        secret = _secret()
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.DecodeError:
        return None
