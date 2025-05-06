"""
Functions to manage websites in the Personal Domain Health Monitor
"""
import sqlite3
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class WebsiteManager:
    """Handles CRUD operations for websites"""
    
    def __init__(self, data_manager):
        self.data_manager = data_manager
    
    def add_website(self, name, url, description=None, check_ssl=True, 
                   check_security=True, alerts_enabled=True, 
                   alert_emails=None, alert_phone=None):
        """
        Add a new website to monitor
        
        Args:
            name (str): Name of the website
            url (str): URL of the website
            description (str, optional): Description
            check_ssl (bool): Whether to check SSL certificate
            check_security (bool): Whether to perform security checks
            alerts_enabled (bool): Whether alerts are enabled
            alert_emails (list, optional): List of email addresses for alerts
            alert_phone (str, optional): Phone number for SMS alerts
            
        Returns:
            int: ID of the new website, or None if failed
        """
        conn = self.data_manager._get_connection()
        cursor = self.data_manager._get_cursor()
        
        try:
            # Ensure URL has scheme
            if not url.startswith(('http://', 'https://')):
                url = f"https://{url}"
                
            # Convert email list to JSON string
            alert_emails_json = json.dumps(alert_emails) if alert_emails else None
            
            cursor.execute('''
            INSERT INTO websites (
                name, url, description, check_ssl, check_security,
                alerts_enabled, alert_emails, alert_phone
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                name, url, description, check_ssl, check_security,
                alerts_enabled, alert_emails_json, alert_phone
            ))
            
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            logger.error(f"Website URL already exists: {url}")
            conn.rollback()
            return None
        except sqlite3.Error as e:
            logger.error(f"Database error adding website: {str(e)}")
            conn.rollback()
            return None
    
    def update_website(self, website_id, **kwargs):
        """
        Update a website's details
        
        Args:
            website_id (int): ID of the website
            **kwargs: Fields to update
            
        Returns:
            bool: True if successful, False otherwise
        """
        conn = self.data_manager._get_connection()
        cursor = self.data_manager._get_cursor()
        
        # Process special fields
        if 'alert_emails' in kwargs and kwargs['alert_emails'] is not None:
            kwargs['alert_emails'] = json.dumps(kwargs['alert_emails'])
            
        # Build update query
        fields = []
        values = []
        
        for key, value in kwargs.items():
            if key in ['name', 'url', 'description', 'check_ssl', 'check_security',
                      'alerts_enabled', 'alert_emails', 'alert_phone']:
                fields.append(f"{key} = ?")
                values.append(value)
        
        if not fields:
            return False
            
        # Add updated_at timestamp
        fields.append("updated_at = ?")
        values.append(datetime.now().isoformat())
        
        # Add website_id
        values.append(website_id)
        
        try:
            query = f"UPDATE websites SET {', '.join(fields)} WHERE id = ?"
            cursor.execute(query, values)
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Database error updating website: {str(e)}")
            conn.rollback()
            return False
    
    def delete_website(self, website_id):
        """
        Delete a website
        
        Args:
            website_id (int): ID of the website
            
        Returns:
            bool: True if successful, False otherwise
        """
        conn = self.data_manager._get_connection()
        cursor = self.data_manager._get_cursor()
        
        try:
            cursor.execute("DELETE FROM websites WHERE id = ?", (website_id,))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Database error deleting website: {str(e)}")
            conn.rollback()
            return False
    
    def get_website(self, website_id):
        """
        Get a website's details
        
        Args:
            website_id (int): ID of the website
            
        Returns:
            dict: Website details
        """
        cursor = self.data_manager._get_cursor()
        
        cursor.execute("SELECT * FROM websites WHERE id = ?", (website_id,))
        
        row = cursor.fetchone()
        if row:
            website = dict(row)
            # Parse JSON fields
            if website.get('alert_emails'):
                try:
                    website['alert_emails'] = json.loads(website['alert_emails'])
                except:
                    website['alert_emails'] = []
            return website
        
        return None
    
    def get_all_websites(self):
        """
        Get all websites
        
        Returns:
            list: All websites
        """
        cursor = self.data_manager._get_cursor()
        
        cursor.execute("SELECT * FROM websites ORDER BY name")
        
        websites = []
        for row in cursor.fetchall():
            website = dict(row)
            # Parse JSON fields
            if website.get('alert_emails'):
                try:
                    website['alert_emails'] = json.loads(website['alert_emails'])
                except:
                    website['alert_emails'] = []
            websites.append(website)
            
        return websites
    
    def search_websites(self, search_term):
        """
        Search for websites
        
        Args:
            search_term (str): Search term
            
        Returns:
            list: Matching websites
        """
        conn = self.data_manager._get_connection()
        cursor = self.data_manager._get_cursor()
        
        cursor.execute('''
        SELECT * FROM websites 
        WHERE name LIKE ? OR url LIKE ? OR description LIKE ?
        ORDER BY name
        ''', (f'%{search_term}%', f'%{search_term}%', f'%{search_term}%'))
        
        websites = []
        for row in cursor.fetchall():
            website = dict(row)
            # Parse JSON fields
            if website.get('alert_emails'):
                try:
                    website['alert_emails'] = json.loads(website['alert_emails'])
                except:
                    website['alert_emails'] = []
            websites.append(website)
            
        return websites
    
    def get_website_stats(self, website_id):
        """
        Get comprehensive statistics for a website
        
        Args:
            website_id (int): ID of the website
            
        Returns:
            dict: Website statistics
        """
        # Get website details
        website = self.get_website(website_id)
        if not website:
            return None
            
        # Get latest check result
        latest_check = self.data_manager.get_latest_check_result(website_id)
        
        # Get uptime percentage
        uptime_7d = self.data_manager.get_uptime_percentage(website_id, days=7)
        uptime_30d = self.data_manager.get_uptime_percentage(website_id, days=30)
        
        # Get response time stats
        response_time_stats = self.data_manager.get_response_time_stats(website_id)
        
        # Get incidents
        incidents = self.data_manager.get_incidents(website_id, limit=5)
        
        # Combine all data
        stats = {
            'website': website,
            'latest_check': latest_check,
            'uptime': {
                '7d': round(uptime_7d, 2),
                '30d': round(uptime_30d, 2)
            },
            'response_time': response_time_stats,
            'incidents': incidents
        }
        
        return stats