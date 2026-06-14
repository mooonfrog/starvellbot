from __future__ import annotations
from typing import Optional

def short_order_id(order_id: Optional[str]) -> str:
    if not order_id:
        return '-'
    cleaned = str(order_id).replace('-', '')
    return cleaned[-8:].upper() if cleaned else '-'
__all__ = ['short_order_id']