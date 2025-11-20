import logging
import os
import sys
from typing import Optional


def setup_logging(
    level: str = "INFO",
    loki_url: Optional[str] = None,
    platform_name: Optional[str] = None
):
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    handlers = [logging.StreamHandler(sys.stdout)]
    
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
            handlers.append(loki_handler)
        except ImportError:
            pass
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to setup Loki handler: {e}")
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
