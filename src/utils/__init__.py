from __future__ import annotations

from typing import Optional


def short_order_id(order_id: Optional[str]) -> str:
    """
    Возвращает короткое отображение идентификатора заказа: последние 8 символов
    исходного UUID в верхнем регистре. Дефисы игнорируются, чтобы результат
    совпадал с тем, что показывается на самом Starvell (например ``C9B26BB0``).

    :param order_id: Полный идентификатор заказа (UUID) или ``None``.
    :return: Короткий идентификатор в верхнем регистре или ``"-"`` если пусто.
    """
    if not order_id:
        return "-"
    cleaned = str(order_id).replace("-", "")
    return cleaned[-8:].upper() if cleaned else "-"


__all__ = ["short_order_id"]
