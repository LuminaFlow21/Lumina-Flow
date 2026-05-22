import logging
import os
import sys
import uuid
import time
from logging.handlers import RotatingFileHandler
from typing import Dict, Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name,
            'timestamp': self.formatTime(record, self.datefmt),
        }

        extras = {k: v for k, v in record.__dict__.items() if k not in logging.LogRecord.__dict__}
        base.update(extras)
        return JsonFormatter._to_json(base)

    @staticmethod
    def _to_json(payload: Dict[str, Any]) -> str:
        try:
            import json
            return json.dumps(payload, ensure_ascii=False)
        except Exception:
            return str(payload)


def _build_formatter(use_json: bool) -> logging.Formatter:
    if use_json:
        return JsonFormatter()
    return logging.Formatter('[%(asctime)s] %(levelname)s in %(name)s: %(message)s')


def setup_logging(config) -> logging.Logger:
    """Configure root logger with console + rotating file handlers."""
    root_logger = logging.getLogger()

    if getattr(root_logger, '_lumina_logging_configured', False):
        return root_logger

    log_level = getattr(logging, str(config.get('LOG_LEVEL', 'INFO')).upper(), logging.INFO)
    root_logger.setLevel(log_level)

    # Remove default handlers added by Flask/werkzeug
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    formatter = _build_formatter(config.get('LOG_JSON', False))

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if config.get('LOG_TO_FILE', True):
        log_dir = config.get('LOG_DIR')
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, 'app.log') if log_dir else 'app.log'
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=config.get('LOG_MAX_BYTES', 5 * 1024 * 1024),
            backupCount=config.get('LOG_BACKUP_COUNT', 5),
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    root_logger._lumina_logging_configured = True
    root_logger.info('Logging configured', extra={'log_level': logging.getLevelName(log_level)})
    return root_logger


def register_request_logging(app):
    """Attach request lifecycle logging hooks to the Flask app once."""
    if getattr(app, '_lumina_request_logging', False):
        return

    from flask import g, request

    @app.before_request
    def start_request_timer():
        g.request_start_time = time.perf_counter()
        g.request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))

    @app.after_request
    def log_request(response):
        try:
            duration_ms = None
            if hasattr(g, 'request_start_time'):
                duration_ms = round((time.perf_counter() - g.request_start_time) * 1000, 2)

            app.logger.info(
                'HTTP request',
                extra={
                    'request_id': getattr(g, 'request_id', None),
                    'method': request.method,
                    'path': request.path,
                    'status': response.status_code,
                    'duration_ms': duration_ms,
                    'remote_addr': request.remote_addr,
                    'user_agent': request.headers.get('User-Agent')
                }
            )
            response.headers['X-Request-ID'] = getattr(g, 'request_id', '')
        except Exception:  # pragma: no cover
            app.logger.exception('Failed to log request')
        return response

    @app.teardown_request
    def log_exception(exc):
        if exc is not None:
            app.logger.exception(
                'Unhandled exception during request',
                extra={'request_id': getattr(g, 'request_id', None)}
            )

    app._lumina_request_logging = True

