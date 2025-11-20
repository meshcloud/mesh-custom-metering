import logging
import os
import sys
from typing import Optional


class ApplicationFilter(logging.Filter):
    def filter(self, record):
        return not record.name.startswith(('urllib3', 'requests', 'charset_normalizer'))


def setup_logging(
    level: str = "INFO",
    loki_url: Optional[str] = None,
    platform_name: Optional[str] = None
):
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    
    handlers = [console_handler]
    
    if loki_url:
        try:
            from logging_loki import LokiHandler
            import time
            
            time.sleep(2)
            
            loki_handler = LokiHandler(
                url=f"{loki_url}/loki/api/v1/push",
                tags={"platform": platform_name or "unknown"},
                version="1",
            )
            loki_handler.addFilter(ApplicationFilter())
            handlers.append(loki_handler)
        except ImportError:
            pass
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to setup Loki handler: {e}")
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers,
        force=True
    )
    
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
