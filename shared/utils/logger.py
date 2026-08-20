"""Logger único con formato compartido."""
import logging

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

def get_logger(name):
    return logging.getLogger(name)

log = get_logger("omniops-qa")
