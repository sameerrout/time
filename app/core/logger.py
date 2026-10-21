import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from app.core.config import LOG_FILE, LOGS_DIR

_logger_initialized = False

class SensitiveFilter(logging.Filter):
    """Filter out any potential password or sensitive credentials from logs."""
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "password" in msg.lower() or "secret" in msg.lower():
            # Redact if encountered
            record.msg = "[REDACTED_SENSITIVE_CONTENT]"
            record.args = ()
        return True

def setup_logging(level=logging.INFO) -> logging.Logger:
    global _logger_initialized
    logger = logging.getLogger("IssueSlipApp")
    
    if _logger_initialized:
        return logger

    logger.setLevel(level)
    logger.propagate = False
    
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)-7s] [%(name)s:%(module)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # 1. Rotating File Handler (5 MB max per file, 3 backups)
    try:
        file_handler = RotatingFileHandler(
            str(LOG_FILE),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(SensitiveFilter())
        logger.addHandler(file_handler)
    except Exception as exc:
        print(f"Warning: Failed to setup file logger: {exc}")
        
    # 2. Console Stream Handler
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(SensitiveFilter())
    logger.addHandler(stream_handler)
    
    _logger_initialized = True
    logger.info("Application logging initialized.")
    return logger

def get_logger(name: str = "IssueSlipApp") -> logging.Logger:
    return logging.getLogger(name)

def get_recent_logs(lines: int = 50) -> list[str]:
    """Retrieve the most recent log entries for diagnostics in the UI."""
    if not LOG_FILE.exists():
        return ["Log file does not exist yet."]
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            return all_lines[-lines:] if len(all_lines) > lines else all_lines
    except Exception as exc:
        return [f"Unable to read log file: {exc}"]
