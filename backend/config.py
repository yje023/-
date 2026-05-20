import os
import sys

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _get_data_dir():
    """数据目录：开发时用 backend/，PyInstaller 打包后用 exe 所在目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return BASE_DIR


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "assessment-system-secret-key-2026")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "assessment-system-jwt-secret-key-2026-long-enough")
    JWT_ACCESS_TOKEN_EXPIRES = 86400
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(_get_data_dir(), 'assessment.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
