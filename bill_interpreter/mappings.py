# bill_interpreter/mappings.py
CHANNEL_MAP = {
    "ea": "active_import",      # Energie Activă (consum)
    "ea prod": "active_export", # Energie Activă livrată (producție)
    "eri": "reactive_import",   # Energie Reactivă Inductivă
    "erc": "reactive_export",   # Energie Reactivă Capacitivă
}

def map_channel(s: str | None) -> str:
    if not s:
        return "active_import"
    return CHANNEL_MAP.get(str(s).strip().lower(), "active_import")