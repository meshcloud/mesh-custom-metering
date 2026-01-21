from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from typing import Dict, Optional


def validate_date(date_string: str, date_format: str) -> bool:
    if not date_string:
        return False
    try:
        datetime.strptime(date_string, date_format)
        return True
    except ValueError:
        return False


def format_date_for_meshstack(year_month: str) -> str:
    return f"{year_month}-01Z"


def get_current_and_last_month(usage_period: Optional[str] = None) -> Dict[str, str]:
    month_format = "%Y-%m"

    if usage_period and validate_date(usage_period, month_format):
        current_month = datetime.strptime(usage_period, month_format)
    else:
        current_month = datetime.combine(
            date.today().replace(day=1), datetime.min.time()
        )

    last_month = current_month - relativedelta(months=1)

    return {
        "current_month": current_month.strftime(month_format),
        "last_month": last_month.strftime(month_format),
    }


def should_process_last_month() -> bool:
    return date.today().day <= 5
