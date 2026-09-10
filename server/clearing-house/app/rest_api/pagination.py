"""Page-number pagination, shared by every list endpoint.

Page numbers rather than cursors because of who reads these lists: the admin
console's table shows "51–100 of 1,240", a page count, and first/last page
buttons. Every one of those needs a total, which a cursor cannot give.

The trade-off, accepted knowingly: when rows arrive while someone is paging,
everything shifts down, and a row can show at the bottom of one page and
again at the top of the next. On a screen a person reads and can refresh,
that is a cosmetic glitch, not wrong data.
"""


def page_count(total: int, limit: int) -> int:
    """Pages needed to show `total` rows, `limit` at a time. 0 when none."""
    # Ceiling division in integers: no float, so no rounding at any size.
    return (total + limit - 1) // limit
