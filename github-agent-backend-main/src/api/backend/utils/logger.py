
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

# Ensure logs directory exists
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "batch_debug.log")

def get_logger(name="batch_processor"):
    """
    Get a configured logger that writes to both console and file
    """
    logger = logging.getLogger(name)
    
    # Only configure if not already configured
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # File Handler (Rotating, max 10MB, keep 5 backups)
        file_handler = RotatingFileHandler(
            LOG_FILE, 
            maxBytes=10*1024*1024, 
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger

# Global instance
batch_logger = get_logger()
