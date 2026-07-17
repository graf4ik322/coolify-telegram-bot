"""Inline-keyboard pagination helper."""

from __future__ import annotations

from dataclasses import dataclass, field

from aiogram.types import InlineKeyboardButton as Btn
from aiogram.types import InlineKeyboardMarkup


@dataclass
class Pagination:
    """Paginated list handler.

    Usage::

        pages = Pagination(items, per_page=5, format_fn=lambda x: x.name)
        markup = pages.build(page=0, callback_prefix="apps")
    """

    items: list
    per_page: int = 5
    format_fn: callable = field(default=lambda x: str(x))

    @property
    def total_pages(self) -> int:
        return max(1, (len(self.items) + self.per_page - 1) // self.per_page)

    def get_page(self, page: int) -> list:
        start = page * self.per_page
        return self.items[start : start + self.per_page]

    def build(self, page: int, callback_prefix: str) -> InlineKeyboardMarkup:
        """Build an inline keyboard for page *page*.

        Each item gets a callback data in the form
        ``<prefix>:item_id`` (using ``item.uuid`` or index).
        """
        rows: list[list[Btn]] = []
        page_items = self.get_page(page)

        for item in page_items:
            label = self.format_fn(item)
            cid = item.uuid if hasattr(item, "uuid") else str(item)
            rows.append([Btn(text=label, callback_data=f"{callback_prefix}:{cid}")])

        # Navigation row
        nav: list[Btn] = []
        if page > 0:
            nav.append(Btn(text="⬅️ Назад", callback_data=f"page:{callback_prefix}:{page - 1}"))
        nav.append(Btn(text=f"{page + 1}/{self.total_pages}", callback_data="noop"))
        if page < self.total_pages - 1:
            nav.append(Btn(text="Вперед ➡️", callback_data=f"page:{callback_prefix}:{page + 1}"))
        if nav:
            rows.append(nav)

        return InlineKeyboardMarkup(inline_keyboard=rows)
