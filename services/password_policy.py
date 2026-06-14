"""Política de força de senha — validação única usada por todos os fluxos que
definem senha (self-service e administração), para que a regra seja consistente.

Retorna a mensagem de erro (str) ou None quando a senha é aceitável.
"""

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def validate_password_strength(password: str | None) -> str | None:
    """Valida a força mínima de uma senha. Retorna a mensagem de erro ou None.

    Exemplo:
        validate_password_strength("curta")          # -> "A senha deve ter ..."
        validate_password_strength("senhaForte12")    # -> None
    """
    if not password:
        return "A senha é obrigatória."
    if not password.strip():
        return "A senha não pode conter apenas espaços."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"A senha deve ter no mínimo {MIN_PASSWORD_LENGTH} caracteres."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"A senha deve ter no máximo {MAX_PASSWORD_LENGTH} caracteres."
    return None
