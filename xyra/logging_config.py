import logging
import os
from xyra.config import settings  # To potentially get LOG_LEVEL if defined in settings

DEFAULT_LOG_LEVEL = "INFO"  # Default to INFO if not set in environment or settings


def setup_logging():
    """
    Configures the root logger for the application.
    """
    log_level_name = os.environ.get(
        "LOG_LEVEL", getattr(settings, "LOG_LEVEL", DEFAULT_LOG_LEVEL)
    ).upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    # For more advanced configuration, consider using logging.config.dictConfig
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler()],  # Ensures logs go to console, good default
    )

    # Example of quieting overly verbose loggers from libraries, if needed in the future
    # logging.getLogger("some_library").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured with level: {logging.getLevelName(log_level)}")


if __name__ == "__main__":
    # Example of how to use it:
    setup_logging()
    logging.getLogger("xyra.test_logger").debug("This is a debug message.")
    logging.getLogger("xyra.test_logger").info("This is an info message.")
    logging.getLogger("xyra.test_logger").warning("This is a warning message.")
    logging.getLogger("xyra.test_logger").error("This is an error message.")
    logging.getLogger("xyra.test_logger").critical("This is a critical message.")
