import logging


def setup_logging() -> None:
    """Configure application logging."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler("smart.log"),
            logging.StreamHandler(),
        ],
    )
