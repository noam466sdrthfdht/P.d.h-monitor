"""
Utility functions for the Personal Domain Health Monitor
"""
import re
import socket
from urllib.parse import urlparse
import platform
import subprocess
import logging
import datetime
import matplotlib.pyplot as plt
import io
import base64
import pandas as pd
from pathlib import Path

logger = logging.getLogger(__name__)

def is_valid_url(url):
    """
    Check if a URL is valid
    
    Args:
        url (str): URL to check
        
    Returns:
        bool: True if valid, False otherwise
    """
    # Add http:// if missing
    if not url.startswith(('http://', 'https://')):
        url = f"https://{url}"
        
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def is_valid_email(email):
    """
    Check if an email address is valid
    
    Args:
        email (str): Email to check
        
    Returns:
        bool: True if valid, False otherwise
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def is_valid_phone(phone):
    """
    Check if a phone number is valid (basic check)
    
    Args:
        phone (str): Phone number to check
        
    Returns:
        bool: True if valid, False otherwise
    """
    # Remove all non-digit characters except leading +
    phone = phone.strip()
    if phone.startswith('+'):
        phone = '+' + re.sub(r'\D', '', phone[1:])
    else:
        phone = re.sub(r'\D', '', phone)
        
    # Check length (E.164 standard: country code + number, typically 7-15 digits)
    return 8 <= len(phone) <= 16

def format_timestamp(timestamp, format="%Y-%m-%d %H:%M:%S"):
    """
    Format a timestamp string
    
    Args:
        timestamp (str): ISO format timestamp
        format (str): Output format
        
    Returns:
        str: Formatted timestamp
    """
    try:
        dt = datetime.datetime.fromisoformat(timestamp)
        return dt.strftime(format)
    except:
        return timestamp

def format_duration(seconds):
    """
    Format duration in seconds to human-readable format
    
    Args:
        seconds (int): Duration in seconds
        
    Returns:
        str: Formatted duration
    """
    if seconds < 60:
        return f"{seconds} seconds"
    elif seconds < 3600:
        minutes = seconds // 60
        remaining_seconds = seconds % 60
        if remaining_seconds == 0:
            return f"{minutes} minutes"
        return f"{minutes} minutes, {remaining_seconds} seconds"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if minutes == 0:
            return f"{hours} hours"
        return f"{hours} hours, {minutes} minutes"

def get_status_color(is_up):
    """
    Get color for status display
    
    Args:
        is_up (bool): Whether the site is up
        
    Returns:
        str: Color code
    """
    return "#28a745" if is_up else "#dc3545"  # Green if up, red if down

def generate_uptime_chart(daily_stats, days=30):
    """
    Generate uptime chart
    
    Args:
        daily_stats (list): Daily statistics
        days (int): Number of days
        
    Returns:
        str: Base64 encoded PNG image
    """
    try:
        # Convert to DataFrame
        df = pd.DataFrame(daily_stats)
        
        if df.empty:
            return None
            
        # Create figure
        plt.figure(figsize=(10, 4))
        plt.plot(df['day'], df['uptime_percentage'], marker='o', linestyle='-', color='#28a745')
        plt.title(f'Uptime Percentage (Last {days} Days)')
        plt.xlabel('Date')
        plt.ylabel('Uptime %')
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.ylim(min(90, df['uptime_percentage'].min() - 5) if not df.empty else 90, 100.5)
        plt.tight_layout()
        
        # Save to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        plt.close()
        
        # Encode
        buf.seek(0)
        img_str = base64.b64encode(buf.read()).decode('utf-8')
        return img_str
    except Exception as e:
        logger.error(f"Error generating uptime chart: {str(e)}")
        return None

def generate_response_time_chart(daily_stats, days=30):
    """
    Generate response time chart
    
    Args:
        daily_stats (list): Daily statistics
        days (int): Number of days
        
    Returns:
        str: Base64 encoded PNG image
    """
    try:
        # Convert to DataFrame
        df = pd.DataFrame(daily_stats)
        
        if df.empty or 'avg_response_time' not in df.columns:
            return None
            
        # Remove None values
        df = df.dropna(subset=['avg_response_time'])
        
        if df.empty:
            return None
            
        # Create figure
        plt.figure(figsize=(10, 4))
        plt.plot(df['day'], df['avg_response_time'], marker='o', linestyle='-', color='#007bff')
        plt.title(f'Average Response Time (Last {days} Days)')
        plt.xlabel('Date')
        plt.ylabel('Response Time (ms)')
        plt.grid(True, linestyle='--', alpha=0.7)
        
        # Set y-limits to some reasonable values
        min_val = max(0, df['avg_response_time'].min() * 0.8) if not df.empty else 0
        max_val = df['avg_response_time'].max() * 1.2 if not df.empty else 1000
        plt.ylim(min_val, max_val)
        
        plt.tight_layout()
        
        # Save to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        plt.close()
        
        # Encode
        buf.seek(0)
        img_str = base64.b64encode(buf.read()).decode('utf-8')
        return img_str
    except Exception as e:
        logger.error(f"Error generating response time chart: {str(e)}")
        return None

def can_resolve_domain(domain):
    """
    Check if a domain can be resolved via DNS
    
    Args:
        domain (str): Domain name
        
    Returns:
        bool: True if resolvable, False otherwise
    """
    try:
        socket.gethostbyname(domain)
        return True
    except socket.gaierror:
        return False

def ping_host(host, count=1, timeout=2):
    """
    Ping a host and return statistics
    
    Args:
        host (str): Hostname or IP
        count (int): Number of packets
        timeout (int): Timeout in seconds
        
    Returns:
        dict: Ping statistics or None if failed
    """
    try:
        # Determine command based on platform
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        timeout_param = '-w' if platform.system().lower() == 'windows' else '-W'
        
        # Build command
        command = ['ping', param, str(count), timeout_param, str(timeout), host]
        
        # Execute command
        output = subprocess.check_output(command, universal_newlines=True)
        
        # Parse output
        if platform.system().lower() == 'windows':
            # Windows output parsing
            try:
                time_ms = re.search(r'Average = (\d+)ms', output)
                time_ms = int(time_ms.group(1)) if time_ms else None
                
                loss = re.search(r'Lost = (\d+)', output)
                loss_count = int(loss.group(1)) if loss else None
                
                return {
                    'min': time_ms,
                    'avg': time_ms,
                    'max': time_ms,
                    'loss': (loss_count / count) * 100 if loss_count is not None else None
                }
            except:
                return None
        else:
            # Unix output parsing
            try:
                # Extract times (min/avg/max/mdev)
                times = re.search(r'= ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)', output)
                if times:
                    min_time = float(times.group(1))
                    avg_time = float(times.group(2))
                    max_time = float(times.group(3))
                else:
                    min_time = avg_time = max_time = None
                
                # Extract packet loss
                loss = re.search(r'(\d+)% packet loss', output)
                loss_pct = int(loss.group(1)) if loss else None
                
                return {
                    'min': min_time,
                    'avg': avg_time,
                    'max': max_time,
                    'loss': loss_pct
                }
            except:
                return None
    except:
        return None

def create_default_config_file(config_path="config.yaml"):
    """
    Create a default configuration file
    
    Args:
        config_path (str): Path to config file
        
    Returns:
        bool: True if created, False if already exists
    """
    if Path(config_path).exists():
        return False
    
    import yaml
    
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
    
    with open(config_path, 'w') as f:
        yaml.dump(default_config, f, default_flow_style=False)
    
    return True

def get_certificate_info(domain, port=443):
    """
    Get detailed SSL certificate information
    
    Args:
        domain (str): Domain name
        port (int): Port number
        
    Returns:
        dict: Certificate information
    """
    try:
        import ssl
        import socket
        from datetime import datetime
        
        context = ssl.create_default_context()
        with socket.create_connection((domain, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                
                # Format not_before date
                not_before = datetime.strptime(cert['notBefore'], "%b %d %H:%M:%S %Y %Z")
                
                # Format not_after date
                not_after = datetime.strptime(cert['notAfter'], "%b %d %H:%M:%S %Y %Z")
                
                # Calculate days remaining
                days_remaining = (not_after - datetime.now()).days
                
                # Extract issuer
                issuer = dict(x[0] for x in cert['issuer'])
                
                # Extract subject
                subject = dict(x[0] for x in cert['subject'])
                
                # Extract SAN
                san = []
                for ext in cert.get('subjectAltName', []):
                    if ext[0] == 'DNS':
                        san.append(ext[1])
                
                return {
                    "issuer": {
                        "organization": issuer.get('organizationName'),
                        "common_name": issuer.get('commonName')
                    },
                    "subject": {
                        "organization": subject.get('organizationName'),
                        "common_name": subject.get('commonName')
                    },
                    "valid_from": not_before.isoformat(),
                    "valid_until": not_after.isoformat(),
                    "days_remaining": days_remaining,
                    "subject_alt_names": san
                }
    except Exception as e:
        return {"error": str(e)}