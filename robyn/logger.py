from enum import Enum
import logging
from typing import Optional
import os


class Colors(Enum):
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"


class Logger:
    HEADER = "\033[95m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def _format_msg(
        self,
        msg: str,
        color: Optional[Colors],
        bold: bool,
        underline: bool,
    ):
        result = msg
        if color is not None:
            result = f"{color.value}{result}{Logger.ENDC}"
        if bold:
            result = f"{Logger.BOLD}{result}"
        if underline:
            result = f"{Logger.UNDERLINE}{result}"
        return result

    def error(
        self,
        msg: str,
        color: Optional[Colors] = Colors.RED,
        bold: bool = False,
        underline: bool = False,
    ):
        self.logger.error(self._format_msg(msg, color, bold, underline))

    def warn(
        self,
        msg: str,
        color: Optional[Colors] = Colors.YELLOW,
        bold: bool = False,
        underline: bool = False,
    ):
        self.logger.warn(self._format_msg(msg, color, bold, underline))

    def info(
        self,
        msg: str,
        color: Optional[Colors] = Colors.GREEN,
        bold: bool = False,
        underline: bool = False,
    ):
        enable_robyn_logs = os.getenv("ENABLE_ROBYN_LOGS")
        if enable_robyn_logs == "true":
            self.logger.info(self._format_msg(msg, color, bold, underline))
        else:
            return

    def debug(
        self,
        msg: str,
        color: Colors = Colors.BLUE,
        bold: bool = False,
        underline: bool = False,
    ):
        enable_robyn_logs = os.getenv("ENABLE_ROBYN_LOGS", "false") == "true"
        if not enable_robyn_logs:
            return


logger = Logger()
