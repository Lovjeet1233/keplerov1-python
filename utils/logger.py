"""
Centralized logging configuration for RAG Service API
"""

import logging
import sys
from pathlib import Path
from datetime import datetime


class Logger:
    """Centralized logger for the application"""
    
    _loggers = {}
    
    @staticmethod
    def setup_logger(
        name: str = "RAGService",
        level: int = logging.INFO,
        log_to_file: bool = True,
        log_dir: str = "logs"
    ) -> logging.Logger:
        """
        Setup and return a logger instance
        
        Args:
            name: Name of the logger
            level: Logging level (default: INFO)
            log_to_file: Whether to log to file (default: True)
            log_dir: Directory for log files (default: 'logs')
            
        Returns:
            Configured logger instance
        """
        # Return existing logger if already configured
        if name in Logger._loggers:
            return Logger._loggers[name]
        
        # Create logger
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.propagate = False
        
        # Remove existing handlers to avoid duplicates
        if logger.hasHandlers():
            logger.handlers.clear()
        
        # Create formatters
        detailed_formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        simple_formatter = logging.Formatter(
            fmt='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Console handler (stdout)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(simple_formatter)
        logger.addHandler(console_handler)
        
        # File handler (if enabled)
        if log_to_file:
            # Create log directory if it doesn't exist
            log_path = Path(log_dir)
            log_path.mkdir(parents=True, exist_ok=True)
            
            # Create log file with timestamp
            log_file = log_path / f"{name}_{datetime.now().strftime('%Y%m%d')}.log"
            
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(level)
            file_handler.setFormatter(detailed_formatter)
            logger.addHandler(file_handler)
        
        # Store logger
        Logger._loggers[name] = logger
        
        return logger
    
    @staticmethod
    def get_logger(name: str = "RAGService") -> logging.Logger:
        """
        Get an existing logger or create a new one with default settings
        
        Args:
            name: Name of the logger
            
        Returns:
            Logger instance
        """
        if name not in Logger._loggers:
            return Logger.setup_logger(name)
        return Logger._loggers[name]


# Create default logger instance
logger = Logger.setup_logger("RAGService")


def log_info(message: str):
    """Log info message"""
    logger.info(message)


def log_error(message: str):
    """Log error message"""
    logger.error(message)


def log_warning(message: str):
    """Log warning message"""
    logger.warning(message)


def log_debug(message: str):
    """Log debug message"""
    logger.debug(message)


def log_exception(message: str, exc_info=True):
    """Log exception with traceback"""
    logger.exception(message, exc_info=exc_info)

