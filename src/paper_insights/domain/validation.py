from __future__ import annotations


def require_tuples(instance: object, *field_names: str) -> None:
    """Reject mutable aliases at immutable DTO boundaries."""
    for field_name in field_names:
        if not isinstance(getattr(instance, field_name), tuple):
            raise ValueError(f"{field_name} must be an immutable tuple")
