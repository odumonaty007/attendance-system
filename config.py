import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()


class Config:
    # Flask secret key
    SECRET_KEY = os.environ.get(
        "SECRET_KEY",
        "dev-secret-key-change-this-in-production"
    )

    # Database configuration
    #
    # If DATABASE_URL is provided, it will be used.
    # Otherwise, the application will use SQLite locally.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL"
    ) or "sqlite:///attendance.db"

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Base URL used when generating QR-code attendance links.
    #
    # LOCAL DEVELOPMENT:
    # http://192.168.1.34:5000
    #
    # RENDER:
    # https://your-attendance-system.onrender.com
    #
    # Render will provide APP_BASE_URL through an environment variable.
    APP_BASE_URL = os.environ.get(
        "APP_BASE_URL",
        "http://192.168.1.34:5000"
    ).rstrip("/")

    # QR Code expiration time in minutes
    QR_CODE_EXPIRATION = 15