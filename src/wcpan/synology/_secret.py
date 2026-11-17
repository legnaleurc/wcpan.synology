"""Credentials must be explicitly revealed at the HTTP boundary."""


class Secret:
    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __str__(self) -> str:
        return "[REDACTED]"

    def __repr__(self) -> str:
        return "Secret([REDACTED])"

    def __format__(self, spec: str) -> str:
        return format(str(self), spec)
