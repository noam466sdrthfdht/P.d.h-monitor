"""
Configuration settings for the Personal Domain Health Monitor
"""
import os
import yaml
from pathlib import Path

class Config:
    """Configuration class for the application"""

    def __init__(self, config_path="config.yaml"):
        self.config_path = config_path
        self._load_config()

    def _load_config(self):
        """Load configuration from YAML file or environment variables"""
        # Default values
        self.DATABASE_PATH = "domain_monitor.db"
        self.CHECK_INTERVAL_MINUTES = 5
        self.RETRY_ATTEMPTS = 2
        self.CONNECTION_TIMEOUT = 10
        self.SMTP_SERVER = ""
        self.SMTP_PORT = 587
        self.SMTP_USERNAME = ""
        self.SMTP_PASSWORD = ""
        self.FROM_EMAIL = ""
        self.TWILIO_ACCOUNT_SID = ""
        self.TWILIO_AUTH_TOKEN = ""
        self.TWILIO_PHONE_NUMBER = ""
        self.DEFAULT_HTTP_HEADERS = {
            "User-Agent": "Domain-Health-Monitor/1.0"
        }

        # Try to load from config file
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as config_file:
                    config_data = yaml.safe_load(config_file)

                if config_data:
                    # Database settings
                    self.DATABASE_PATH = config_data.get('database_path', self.DATABASE_PATH)

                    # Monitor settings
                    monitor_settings = config_data.get('monitor_settings', {})
                    self.CHECK_INTERVAL_MINUTES = monitor_settings.get('check_interval_minutes', self.CHECK_INTERVAL_MINUTES)
                    self.RETRY_ATTEMPTS = monitor_settings.get('retry_attempts', self.RETRY_ATTEMPTS)
                    self.CONNECTION_TIMEOUT = monitor_settings.get('connection_timeout', self.CONNECTION_TIMEOUT)

                    # Email settings
                    email_settings = config_data.get('email_settings', {})
                    self.SMTP_SERVER = email_settings.get('smtp_server', self.SMTP_SERVER)
                    self.SMTP_PORT = email_settings.get('smtp_port', self.SMTP_PORT)
                    self.SMTP_USERNAME = email_settings.get('smtp_username', self.SMTP_USERNAME)
                    self.SMTP_PASSWORD = email_settings.get('smtp_password', self.SMTP_PASSWORD)
                    self.FROM_EMAIL = email_settings.get('from_email', self.FROM_EMAIL)

                    # SMS settings
                    sms_settings = config_data.get('sms_settings', {})
                    self.TWILIO_ACCOUNT_SID = sms_settings.get('twilio_account_sid', self.TWILIO_ACCOUNT_SID)
                    self.TWILIO_AUTH_TOKEN = sms_settings.get('twilio_auth_token', self.TWILIO_AUTH_TOKEN)
                    self.TWILIO_PHONE_NUMBER = sms_settings.get('twilio_phone_number', self.TWILIO_PHONE_NUMBER)

                    # HTTP settings
                    http_settings = config_data.get('http_settings', {})
                    headers = http_settings.get('default_headers', {})
                    if headers:
                        self.DEFAULT_HTTP_HEADERS.update(headers)

            except Exception as e:
                print(f"Error loading config file: {str(e)}")

        # Override with environment variables if present
        self.DATABASE_PATH = os.environ.get('DOMAIN_MONITOR_DB_PATH', self.DATABASE_PATH)
        self.CHECK_INTERVAL_MINUTES = int(os.environ.get('DOMAIN_MONITOR_CHECK_INTERVAL', self.CHECK_INTERVAL_MINUTES))
        self.RETRY_ATTEMPTS = int(os.environ.get('DOMAIN_MONITOR_RETRY_ATTEMPTS', self.RETRY_ATTEMPTS))
        self.CONNECTION_TIMEOUT = int(os.environ.get('DOMAIN_MONITOR_TIMEOUT', self.CONNECTION_TIMEOUT))
        self.SMTP_SERVER = os.environ.get('DOMAIN_MONITOR_SMTP_SERVER', self.SMTP_SERVER)
        self.SMTP_PORT = int(os.environ.get('DOMAIN_MONITOR_SMTP_PORT', self.SMTP_PORT))
        self.SMTP_USERNAME = os.environ.get('DOMAIN_MONITOR_SMTP_USERNAME', self.SMTP_USERNAME)
        self.SMTP_PASSWORD = os.environ.get('DOMAIN_MONITOR_SMTP_PASSWORD', self.SMTP_PASSWORD)
        self.FROM_EMAIL = os.environ.get('DOMAIN_MONITOR_FROM_EMAIL', self.FROM_EMAIL)
        self.TWILIO_ACCOUNT_SID = os.environ.get('DOMAIN_MONITOR_TWILIO_SID', self.TWILIO_ACCOUNT_SID)
        self.TWILIO_AUTH_TOKEN = os.environ.get('DOMAIN_MONITOR_TWILIO_TOKEN', self.TWILIO_AUTH_TOKEN)
        self.TWILIO_PHONE_NUMBER = os.environ.get('DOMAIN_MONITOR_TWILIO_PHONE', self.TWILIO_PHONE_NUMBER)

        # Ensure database directory exists
        db_dir = os.path.dirname(self.DATABASE_PATH)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)

    def create_default_config(self):
        """Create a default configuration file if none exists"""
        if os.path.exists(self.config_path):
            return False

        default_config = {
            "database_path": "domain_monitor.db",
            "monitor_settings": {
                "check_interval_minutes": 5,
                "retry_attempts": 2,
                "connection_timeout": 10
            },
            "email_settings": {
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "smtp_username": "your_email@gmail.com",
                "smtp_password": "your_app_password",
                "from_email": "your_email@gmail.com"
            },
            "sms_settings": {
                "twilio_account_sid": "your_twilio_account_sid",
                "twilio_auth_token": "your_twilio_auth_token",
                "twilio_phone_number": "your_twilio_phone_number"
            },
            "http_settings": {
                "default_headers": {
                    "User-Agent": "Domain-Health-Monitor/1.0"
                }
            }
        }

        with open(self.config_path, 'w') as config_file:
            yaml.dump(default_config, config_file, default_flow_style=False)

        return True
    def save_config(self, config_data):
        """
        Save configuration to the YAML file

        Args:
            config_data (dict): Configuration data to save
        """
        import yaml
        with open(self.config_path, 'w') as config_file:
            yaml.dump(config_data, config_file, default_flow_style=False)

        # Update current settings
        self._load_config()

        return True
