import phonenumbers

DEFAULT_REGION = "RU"


def normalize_phone(value: str, region: str = DEFAULT_REGION) -> str:
    """
    Приводит номер телефона к формату E.164 (+79998889999)
    """
    try:
        number = phonenumbers.parse(value, region)
    except phonenumbers.NumberParseException as exc:
        raise ValueError(f"Некорректный телефон: {value}") from exc

    if not phonenumbers.is_valid_number(number):
        raise ValueError(f"Некорректный телефон: {value}")

    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
