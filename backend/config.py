import os
import sys

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _get_data_dir():
    """数据目录：开发时用 backend/，PyInstaller 打包后用 exe 所在目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return BASE_DIR


def _load_or_create_secret(filename):
    """从文件读取密钥，不存在则随机生成并持久化"""
    secret_file = os.path.join(_get_data_dir(), filename)
    if os.path.exists(secret_file):
        with open(secret_file) as f:
            return f.read().strip()
    secret = os.urandom(32).hex()
    with open(secret_file, 'w') as f:
        f.write(secret)
    return secret


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or _load_or_create_secret(".secret_key")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY") or _load_or_create_secret(".jwt_secret_key")
    JWT_ACCESS_TOKEN_EXPIRES = 86400
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(_get_data_dir(), 'assessment.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
