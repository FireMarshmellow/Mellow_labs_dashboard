from datetime import date

UK_TAX_YEAR_START_MONTH = 4
UK_TAX_YEAR_START_DAY = 6


def tax_year_for(d: date) -> str:
    start_this_year = date(d.year, UK_TAX_YEAR_START_MONTH, UK_TAX_YEAR_START_DAY)
    if d >= start_this_year:
        return f"{d.year}-{(d.year + 1) % 100:02d}"
    else:
        return f"{d.year - 1}-{d.year % 100:02d}"


def tax_year_bounds(year_start: int) -> tuple[date, date]:
    """Return (start, end_inclusive) for tax year starting year_start (e.g., 2024 for 2024-25)."""
    start = date(year_start, 4, 6)
    end = date(year_start + 1, 4, 5)
    return start, end
