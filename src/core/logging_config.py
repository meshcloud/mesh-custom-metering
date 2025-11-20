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
            
            loki_handler = LokiHandler(
                url=loki_url,
                tags={"platform": platform_name or "unknown"},
                version="1",
            )
            handlers.append(loki_handler)
        except ImportError:
            logging.warning("logging_loki not installed, skipping Loki integration")
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
