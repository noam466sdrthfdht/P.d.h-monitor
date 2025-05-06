#!/usr/bin/env python3
"""
Personal Domain Health Monitor
Desktop application entry point
"""
import os
import sys
import time
import logging
import threading
import webview
import socket
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import json
from config import Config
from domain_monitor import DomainMonitor
from data_manager import DataManager
from notification_manager import NotificationManager
from dashboard import create_app
from website_manager import WebsiteManager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("domain_monitor.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Global variables for components
config = None
data_manager = None
notification_manager = None
domain_monitor = None
website_manager = None
scheduler = None
flask_app = None

def monitor_task():
    """Scheduled task to monitor all domains"""
    logger.info("Running scheduled domain health check")
    websites = website_manager.get_all_websites()

    # Track completion time for UI updates
    check_results = {
        'timestamp': datetime.now().isoformat(),
        'websites_checked': 0,
        'websites_up': 0,
        'websites_down': 0
    }

    for website in websites:
        try:
            result = domain_monitor.check_domain(
                website['url'],
                check_ssl=website.get('check_ssl', True),
                check_security=website.get('check_security', True)
            )

            # Store results
            data_manager.store_check_result(website['id'], result)

            # Update stats
            check_results['websites_checked'] += 1
            if result['is_up']:
                check_results['websites_up'] += 1
            else:
                check_results['websites_down'] += 1

            # Check for alerts
            if not result['is_up'] and website.get('alerts_enabled', True):
                notification_manager.send_alert(
                    website['name'],
                    website['url'],
                    result['status_code'],
                    result['response_time'],
                    website.get('alert_emails', []),
                    website.get('alert_phone', None)
                )

            logger.info(f"Checked {website['url']} - Status: {'Up' if result['is_up'] else 'Down'}")
        except Exception as e:
            logger.error(f"Error checking {website['url']}: {str(e)}")

    # Save the last check results to a file that the UI can access
    try:
        with open('last_check.json', 'w') as f:
            json.dump(check_results, f)
    except Exception as e:
        logger.error(f"Error saving check results: {str(e)}")

    logger.info(f"Completed domain health check: {check_results['websites_up']} up, {check_results['websites_down']} down")


def start_scheduler(interval_minutes=5):
    """Start the background scheduler for regular checks"""
    scheduler = BackgroundScheduler()
    scheduler.add_job(monitor_task, 'interval', minutes=interval_minutes)
    scheduler.start()
    logger.info(f"Scheduler started with {interval_minutes} minute interval")
    return scheduler

def run_flask_app():
    """Run the Flask dashboard app"""
    global flask_app
    try:
        flask_app = create_app(data_manager, website_manager, domain_monitor)
        flask_app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        logger.error(f"Error starting Flask app: {e}")

def initialize_components():
    """Initialize all components"""
    global config, data_manager, notification_manager, domain_monitor, website_manager

    # Initialize components
    config = Config()
    data_manager = DataManager(config.DATABASE_PATH)
    notification_manager = NotificationManager(
        config.SMTP_SERVER,
        config.SMTP_PORT,
        config.SMTP_USERNAME,
        config.SMTP_PASSWORD,
        config.FROM_EMAIL,
        config.TWILIO_ACCOUNT_SID,
        config.TWILIO_AUTH_TOKEN,
        config.TWILIO_PHONE_NUMBER
    )
    domain_monitor = DomainMonitor()
    website_manager = WebsiteManager(data_manager)

    # Ensure database and tables exist
    data_manager.initialize_database()

def is_port_in_use(port):
    """Check if a port is in use"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def start_app():
    """Start the desktop application"""
    # Set the working directory to the script location
    if getattr(sys, 'frozen', False):
        # Running as compiled exe
        os.chdir(os.path.dirname(sys.executable))
    else:
        # Running as script
        os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Initialize all components
    initialize_components()

    # Start the monitoring scheduler in the background
    global scheduler
    scheduler = start_scheduler(config.CHECK_INTERVAL_MINUTES)

    try:
        # Run initial check
        monitor_task()

        # Start the Flask app in a separate thread
        logger.info("Starting web dashboard")
        flask_thread = threading.Thread(target=run_flask_app)
        flask_thread.daemon = True
        flask_thread.start()

        # Wait for Flask to start by checking if the port is in use
        logger.info("Waiting for Flask server to start...")
        wait_time = 0
        while not is_port_in_use(5000) and wait_time < 20:
            time.sleep(1)
            wait_time += 1
            logger.info(f"Waiting for Flask... ({wait_time}s)")

        if not is_port_in_use(5000):
            logger.error("Flask server failed to start within timeout")
            if scheduler:
                scheduler.shutdown()
            sys.exit(1)

        logger.info("Flask server started successfully!")

        # Create the window
        window = webview.create_window(
            title='Domain Health Monitor',
            url='http://127.0.0.1:5000',
            width=1200,
            height=800,
            resizable=True,
            min_size=(800, 600),
            text_select=True,
            confirm_close=True,
            background_color='#FFFFFF'
        )

        # Start the webview
        logger.info("Starting web view...")
        webview.start()

    except KeyboardInterrupt:
        logger.info("Application shutting down")
        if scheduler:
            scheduler.shutdown()
    except Exception as e:
        logger.error(f"Error starting application: {str(e)}")
        if scheduler:
            scheduler.shutdown()
        raise

if __name__ == "__main__":
    start_app()
