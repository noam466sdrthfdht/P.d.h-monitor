"""
Core monitoring functionality for the Personal Domain Health Monitor
"""
import time
import socket
import ssl
import logging
import requests
from datetime import datetime
import OpenSSL.crypto as crypto
from urllib.parse import urlparse
import subprocess
import platform

from utils import is_valid_url

logger = logging.getLogger(__name__)

class DomainMonitor:
    """Handles website monitoring and health checks"""
    
    def __init__(self, timeout=10, retry_attempts=2, default_headers=None):
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.default_headers = default_headers or {
            "User-Agent": "Domain-Health-Monitor/1.0"
        }
    
    def check_domain(self, url, check_ssl=True, check_security=True):
        """
        Perform a comprehensive health check on a domain
        
        Args:
            url (str): The URL to check
            check_ssl (bool): Whether to check SSL certificate
            check_security (bool): Whether to perform security checks
            
        Returns:
            dict: Result of the health check
        """
        if not is_valid_url(url):
            raise ValueError(f"Invalid URL format: {url}")
            
        # Ensure URL has scheme
        if not url.startswith(('http://', 'https://')):
            url = f"https://{url}"
            
        result = {
            'url': url,
            'timestamp': datetime.now().isoformat(),
            'is_up': False,
            'status_code': None,
            'response_time': None,
            'error': None,
            'ssl_valid': None,
            'ssl_days_remaining': None,
            'security_score': None,
            'ping_time': None,
            'redirect_url': None,
            'content_size': None
        }
        
        # Ping check
        result['ping_time'] = self._ping_domain(urlparse(url).netloc)
        
        # HTTP check
        for attempt in range(self.retry_attempts):
            try:
                start_time = time.time()
                response = requests.get(
                    url, 
                    timeout=self.timeout,
                    headers=self.default_headers,
                    allow_redirects=True
                )
                end_time = time.time()
                
                result['response_time'] = round((end_time - start_time) * 1000, 2)  # in ms
                result['status_code'] = response.status_code
                result['is_up'] = 200 <= response.status_code < 400
                result['content_size'] = len(response.content)
                
                # Check if redirected
                if response.url != url:
                    result['redirect_url'] = response.url
                
                break  # Success, no need to retry
                
            except requests.RequestException as e:
                result['error'] = str(e)
                # If we've tried all attempts, just continue with other checks
                if attempt == self.retry_attempts - 1:
                    logger.warning(f"Failed to connect to {url} after {self.retry_attempts} attempts: {str(e)}")
                else:
                    time.sleep(1)  # Wait before retry
        
        # SSL certificate check
        if check_ssl and urlparse(url).scheme == 'https':
            ssl_result = self._check_ssl_certificate(urlparse(url).netloc)
            result.update(ssl_result)
            
        # Security checks
        if check_security and result['is_up']:
            security_result = self._perform_security_checks(url, response if 'response' in locals() else None)
            result.update(security_result)
            
        return result
    
    def _ping_domain(self, domain):
        """
        Ping a domain and return the response time
        
        Args:
            domain (str): Domain name to ping
            
        Returns:
            float or None: Ping time in ms, or None if failed
        """
        try:
            # Different ping command parameters based on OS
            param = '-n' if platform.system().lower() == 'windows' else '-c'
            command = ['ping', param, '1', domain]
            
            output = subprocess.check_output(command, universal_newlines=True)
            
            # Parse the output to get the time
            if platform.system().lower() == 'windows':
                try:
                    # Windows format: "time=<time>ms"
                    time_str = output.split('time=')[1].split('ms')[0].strip()
                    return float(time_str)
                except:
                    return None
            else:
                try:
                    # Unix format: "time=<time> ms"
                    time_str = output.split('time=')[1].split(' ms')[0].strip()
                    return float(time_str)
                except:
                    return None
        except:
            return None
    
    def _check_ssl_certificate(self, domain, port=443):
        """
        Check SSL certificate validity and expiration
        
        Args:
            domain (str): Domain name to check
            port (int): Port to connect to
            
        Returns:
            dict: SSL check results
        """
        result = {
            'ssl_valid': False,
            'ssl_days_remaining': None,
            'ssl_issuer': None,
            'ssl_error': None
        }
        
        try:
            # Create SSL context
            context = ssl.create_default_context()
            conn = context.wrap_socket(
                socket.socket(socket.AF_INET),
                server_hostname=domain
            )
            
            # Connect to the server
            conn.settimeout(self.timeout)
            conn.connect((domain, port))
            
            # Get certificate
            ssl_info = conn.getpeercert()
            
            # Extract issuer
            issuer = dict(x[0] for x in ssl_info['issuer'])
            result['ssl_issuer'] = issuer.get('organizationName', issuer.get('commonName', 'Unknown'))
            
            # Check expiration
            expires = ssl_info['notAfter']
            expires_datetime = datetime.strptime(expires, "%b %d %H:%M:%S %Y %Z")
            days_remaining = (expires_datetime - datetime.now()).days
            
            result['ssl_days_remaining'] = days_remaining
            result['ssl_valid'] = days_remaining > 0
            
            conn.close()
            
        except ssl.SSLError as e:
            result['ssl_error'] = f"SSL Error: {str(e)}"
        except socket.error as e:
            result['ssl_error'] = f"Socket Error: {str(e)}"
        except Exception as e:
            result['ssl_error'] = f"Error: {str(e)}"
            
        return result
        
    def _perform_security_checks(self, url, response=None):
        """
        Perform basic security checks on a website
        
        Args:
            url (str): URL to check
            response (requests.Response): Response object if available
            
        Returns:
            dict: Security check results
        """
        security_result = {
            'security_score': 0,
            'security_issues': []
        }
        
        total_checks = 0
        passed_checks = 0
        
        # Check if using HTTPS
        if url.startswith('https://'):
            passed_checks += 1
        else:
            security_result['security_issues'].append('Not using HTTPS')
        total_checks += 1
        
        # More checks if we have a response
        if response:
            # Check for security headers
            headers = response.headers
            
            # Check for Content-Security-Policy
            if 'Content-Security-Policy' in headers:
                passed_checks += 1
            else:
                security_result['security_issues'].append('Missing Content-Security-Policy header')
            total_checks += 1
            
            # Check for X-XSS-Protection
            if 'X-XSS-Protection' in headers:
                passed_checks += 1
            else:
                security_result['security_issues'].append('Missing X-XSS-Protection header')
            total_checks += 1
            
            # Check for X-Content-Type-Options
            if 'X-Content-Type-Options' in headers:
                passed_checks += 1
            else:
                security_result['security_issues'].append('Missing X-Content-Type-Options header')
            total_checks += 1
            
            # Check for Strict-Transport-Security
            if 'Strict-Transport-Security' in headers:
                passed_checks += 1
            else:
                security_result['security_issues'].append('Missing Strict-Transport-Security header')
            total_checks += 1
            
            # Check for X-Frame-Options
            if 'X-Frame-Options' in headers:
                passed_checks += 1
            else:
                security_result['security_issues'].append('Missing X-Frame-Options header')
            total_checks += 1
            
            # Check for Referrer-Policy
            if 'Referrer-Policy' in headers:
                passed_checks += 1
            else:
                security_result['security_issues'].append('Missing Referrer-Policy header')
            total_checks += 1
        
        # Calculate security score (as a percentage)
        if total_checks > 0:
            security_result['security_score'] = int((passed_checks / total_checks) * 100)
            
        return security_result
    
    def get_ssl_info(self, domain, port=443):
        """
        Get detailed SSL certificate information
        
        Args:
            domain (str): Domain name
            port (int): Port number
            
        Returns:
            dict: Detailed SSL certificate information
        """
        try:
            # Connect to the server and get certificate
            context = ssl.create_default_context()
            with socket.create_connection((domain, port)) as sock:
                with context.wrap_socket(sock, server_hostname=domain) as ssock:
                    cert_bin = ssock.getpeercert(binary_form=True)
                    
            # Parse certificate
            x509 = crypto.load_certificate(crypto.FILETYPE_ASN1, cert_bin)
            
            # Get certificate details
            issuer = x509.get_issuer()
            subject = x509.get_subject()
            
            # Format expiration time
            not_after = datetime.strptime(x509.get_notAfter().decode('utf-8'), "%Y%m%d%H%M%SZ")
            days_remaining = (not_after - datetime.now()).days
            
            cert_info = {
                'issuer': {
                    'organization': issuer.O,
                    'common_name': issuer.CN,
                    'country': issuer.C
                },
                'subject': {
                    'organization': subject.O,
                    'common_name': subject.CN,
                    'country': subject.C
                },
                'version': x509.get_version(),
                'serial_number': x509.get_serial_number(),
                'not_before': datetime.strptime(x509.get_notBefore().decode('utf-8'), "%Y%m%d%H%M%SZ").isoformat(),
                'not_after': not_after.isoformat(),
                'days_remaining': days_remaining,
                'has_expired': x509.has_expired()
            }
            
            # Get all SANs (Subject Alternative Names)
            san_list = []
            for i in range(x509.get_extension_count()):
                ext = x509.get_extension(i)
                if ext.get_short_name() == b'subjectAltName':
                    san_text = ext.__str__()
                    # Parse SANs (format: "DNS:example.com, DNS:www.example.com")
                    for san in san_text.split(', '):
                        if san.startswith('DNS:'):
                            san_list.append(san[4:])
            
            cert_info['subject_alt_names'] = san_list
            
            return cert_info
        except Exception as e:
            return {'error': str(e)}