import json
from fastapi import Query

class ListParams:
    def __init__(
        self,
        _page: int = Query(1),
        _perPage: int = Query(10),
        _sort: str | None = Query(None),
        _order: str = Query("ASC"),
        filter: str | None = Query(None),
    ):
        self.page     = _page
        self.per_page = _perPage
        self.sort     = _sort
        self.order    = _order.upper()
        self.filters  = json.loads(filter) if filter else {}
        self.total    = 0
