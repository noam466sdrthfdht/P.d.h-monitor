"""
Notification system for the Personal Domain Health Monitor
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# Import Twilio client for SMS alerts
try:
    from twilio.rest import Client
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False

logger = logging.getLogger(__name__)

class NotificationManager:
    """Handles sending email and SMS alerts"""
    
    def __init__(self, smtp_server, smtp_port, smtp_username, smtp_password, 
                 from_email, twilio_account_sid=None, twilio_auth_token=None, 
                 twilio_phone_number=None):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password
        self.from_email = from_email
        
        # Twilio settings for SMS
        self.twilio_account_sid = twilio_account_sid
        self.twilio_auth_token = twilio_auth_token
        self.twilio_phone_number = twilio_phone_number
        self.twilio_client = None
        
        # Initialize Twilio client if credentials provided
        if TWILIO_AVAILABLE and twilio_account_sid and twilio_auth_token:
            try:
                self.twilio_client = Client(twilio_account_sid, twilio_auth_token)
                logger.info("Twilio client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Twilio client: {str(e)}")
    
    def send_alert(self, website_name, website_url, status_code, response_time, 
                  email_recipients=None, phone_number=None):
        """
        Send alerts when a website goes down
        
        Args:
            website_name (str): Name of the website
            website_url (str): URL of the website
            status_code (int): HTTP status code
            response_time (float): Response time in ms
            email_recipients (list): List of email addresses
            phone_number (str): Phone number for SMS
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Format the alert message
        subject = f"🚨 ALERT: {website_name} is DOWN!"
        
        message = f"""
        ⚠️ Domain Health Monitor Alert ⚠️
        
        Website: {website_name}
        URL: {website_url}
        Status: DOWN
        Time: {timestamp}
        Status Code: {status_code or 'N/A'}
        Response Time: {response_time or 'N/A'} ms
        
        Please check your website as soon as possible.
        
        ---
        This is an automated alert from your Domain Health Monitor.
        """
        
        # Send email alerts
        if email_recipients:
            self._send_email_alert(subject, message, email_recipients)
            
        # Send SMS alert
        if phone_number:
            sms_message = f"ALERT: {website_name} ({website_url}) is DOWN! Status: {status_code or 'N/A'}. Please check ASAP."
            self._send_sms_alert(sms_message, phone_number)
    
    def send_recovery_notification(self, website_name, website_url, downtime_duration,
                                 email_recipients=None, phone_number=None):
        """
        Send notification when a website recovers
        
        Args:
            website_name (str): Name of the website
            website_url (str): URL of the website
            downtime_duration (int): Downtime duration in seconds
            email_recipients (list): List of email addresses
            phone_number (str): Phone number for SMS
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Format duration nicely
        if downtime_duration < 60:
            duration_str = f"{downtime_duration} seconds"
        elif downtime_duration < 3600:
            minutes = downtime_duration // 60
            seconds = downtime_duration % 60
            duration_str = f"{minutes} minutes, {seconds} seconds"
        else:
            hours = downtime_duration // 3600
            minutes = (downtime_duration % 3600) // 60
            duration_str = f"{hours} hours, {minutes} minutes"
        
        # Format the recovery message
        subject = f"✅ RECOVERED: {website_name} is back online"
        
        message = f"""
        ✅ Domain Health Monitor Recovery Notification ✅
        
        Website: {website_name}
        URL: {website_url}
        Status: RECOVERED
        Time: {timestamp}
        Downtime Duration: {duration_str}
        
        Your website is now back online.
        
        ---
        This is an automated notification from your Domain Health Monitor.
        """
        
        # Send email alerts
        if email_recipients:
            self._send_email_alert(subject, message, email_recipients)
            
        # Send SMS alert
        if phone_number:
            sms_message = f"RECOVERED: {website_name} ({website_url}) is back online after {duration_str} of downtime."
            self._send_sms_alert(sms_message, phone_number)
    
    def send_ssl_expiry_alert(self, website_name, website_url, days_remaining,
                            email_recipients=None, phone_number=None):
        """
        Send alert when SSL certificate is close to expiry
        
        Args:
            website_name (str): Name of the website
            website_url (str): URL of the website
            days_remaining (int): Days until SSL certificate expires
            email_recipients (list): List of email addresses
            phone_number (str): Phone number for SMS
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Format the alert message
        subject = f"🔒 SSL Certificate Expiring: {website_name}"
        
        message = f"""
        🔒 Domain Health Monitor SSL Alert 🔒
        
        Website: {website_name}
        URL: {website_url}
        Alert Time: {timestamp}
        
        Your SSL certificate will expire in {days_remaining} days.
        Please renew your SSL certificate before it expires to avoid security warnings.
        
        ---
        This is an automated alert from your Domain Health Monitor.
        """
        
        # Send email alerts
        if email_recipients:
            self._send_email_alert(subject, message, email_recipients)
            
        # Send SMS alert
        if phone_number:
            sms_message = f"SSL ALERT: {website_name} SSL certificate expires in {days_remaining} days. Please renew it soon."
            self._send_sms_alert(sms_message, phone_number)
    
    def _send_email_alert(self, subject, message_text, recipients):
        """
        Send email alert
        
        Args:
            subject (str): Email subject
            message_text (str): Email body
            recipients (list): List of email addresses
        """
        if not self.smtp_server or not self.smtp_username or not self.from_email:
            logger.warning("Email settings not configured, skipping email alert")
            return
            
        if not recipients:
            return
            
        # Create message
        msg = MIMEMultipart()
        msg['From'] = self.from_email
        msg['To'] = ', '.join(recipients)
        msg['Subject'] = subject
        
        # Attach message text
        msg.attach(MIMEText(message_text, 'plain'))
        
        try:
            # Connect to SMTP server
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
                
            logger.info(f"Email alert sent to {len(recipients)} recipients")
        except Exception as e:
            logger.error(f"Failed to send email alert: {str(e)}")
    
    def _send_sms_alert(self, message, phone_number):
        """
        Send SMS alert using Twilio
        
        Args:
            message (str): SMS message
            phone_number (str): Recipient phone number
        """
        if not TWILIO_AVAILABLE:
            logger.warning("Twilio package not installed, skipping SMS alert")
            return
            
        if not self.twilio_client or not self.twilio_phone_number:
            logger.warning("Twilio not configured, skipping SMS alert")
            return
            
        if not phone_number:
            return
            
        try:
            # Send SMS via Twilio
            sms = self.twilio_client.messages.create(
                body=message,
                from_=self.twilio_phone_number,
                to=phone_number
            )
            
            logger.info(f"SMS alert sent to {phone_number}, SID: {sms.sid}")
        except Exception as e:
            logger.error(f"Failed to send SMS alert: {str(e)}")
    
    def test_email_notification(self, recipient):
        """
        Send a test email notification
        
        Args:
            recipient (str): Email address
            
        Returns:
            bool: True if successful, False otherwise
        """
        subject = "Domain Health Monitor - Test Email"
        message = """
        This is a test email from your Domain Health Monitor.
        
        If you're receiving this, your email notifications are working correctly.
        
        Time: {}
        
        ---
        Domain Health Monitor
        """.format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        try:
            self._send_email_alert(subject, message, [recipient])
            return True
        except Exception as e:
            logger.error(f"Test email failed: {str(e)}")
            return False
    
    def test_sms_notification(self, phone_number):
        """
        Send a test SMS notification
        
        Args:
            phone_number (str): Phone number
            
        Returns:
            bool: True if successful, False otherwise
        """
        message = "Domain Health Monitor - Test SMS. If you're receiving this, your SMS notifications are working correctly."
        
        try:
            self._send_sms_alert(message, phone_number)
            return True
        except Exception as e:
            logger.error(f"Test SMS failed: {str(e)}")
            return False