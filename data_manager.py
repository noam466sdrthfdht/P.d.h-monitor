"""
Data storage and retrieval for the Personal Domain Health Monitor
"""
import os
import sqlite3
import json
import logging
import threading
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class DataManager:
    """
    Handles data storage and retrieval for the application.
    Uses SQLite for storing website data and check results.
    """
    
    # Thread-local storage for connections
    _local = threading.local()
    
    def __init__(self, db_path):
        self.db_path = db_path
    
    def _get_connection(self):
        """Get a thread-local database connection"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            # Enable foreign keys
            self._local.conn.execute("PRAGMA foreign_keys = ON")
            # Return rows as dictionaries
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn
    
    def _get_cursor(self):
        """Get a thread-local database cursor"""
        if not hasattr(self._local, 'cursor') or self._local.cursor is None:
            self._local.cursor = self._get_connection().cursor()
        return self._local.cursor
    
    def close(self):
        """Close the database connection"""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
            self._local.cursor = None
    
    def initialize_database(self):
        """Create database tables if they don't exist"""
        conn = self._get_connection()
        cursor = self._get_cursor()
        
        # Create websites table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS websites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            description TEXT,
            check_ssl BOOLEAN DEFAULT 1,
            check_security BOOLEAN DEFAULT 1,
            alerts_enabled BOOLEAN DEFAULT 1,
            alert_emails TEXT,
            alert_phone TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Create check_results table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS check_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            website_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_up BOOLEAN,
            status_code INTEGER,
            response_time REAL,
            error TEXT,
            ssl_valid BOOLEAN,
            ssl_days_remaining INTEGER,
            security_score INTEGER,
            ping_time REAL,
            redirect_url TEXT,
            content_size INTEGER,
            details TEXT,
            FOREIGN KEY (website_id) REFERENCES websites(id) ON DELETE CASCADE
        )
        ''')
        
        # Create incidents table (for tracking downtime)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            website_id INTEGER,
            start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_time TIMESTAMP,
            duration INTEGER,
            resolved BOOLEAN DEFAULT 0,
            notes TEXT,
            FOREIGN KEY (website_id) REFERENCES websites(id) ON DELETE CASCADE
        )
        ''')
        
        conn.commit()
    
    def store_check_result(self, website_id, result):
        """
        Store a check result in the database
        
        Args:
            website_id (int): ID of the website
            result (dict): Check result
        """
        conn = self._get_connection()
        cursor = self._get_cursor()
        
        # Convert any complex data to JSON string
        details = {k: v for k, v in result.items() if k not in [
            'url', 'timestamp', 'is_up', 'status_code', 'response_time', 
            'error', 'ssl_valid', 'ssl_days_remaining', 'security_score',
            'ping_time', 'redirect_url', 'content_size'
        ]}
        
        try:
            cursor.execute('''
            INSERT INTO check_results (
                website_id, timestamp, is_up, status_code, response_time,
                error, ssl_valid, ssl_days_remaining, security_score,
                ping_time, redirect_url, content_size, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                website_id,
                result.get('timestamp', datetime.now().isoformat()),
                result.get('is_up', False),
                result.get('status_code'),
                result.get('response_time'),
                result.get('error'),
                result.get('ssl_valid'),
                result.get('ssl_days_remaining'),
                result.get('security_score'),
                result.get('ping_time'),
                result.get('redirect_url'),
                result.get('content_size'),
                json.dumps(details) if details else None
            ))
            
            conn.commit()
            
            # Check if need to create or resolve an incident
            self._update_incidents(website_id, result.get('is_up', False))
            
        except sqlite3.Error as e:
            logger.error(f"Database error storing check result: {str(e)}")
            conn.rollback()
    
    def _update_incidents(self, website_id, is_up):
        """
        Update incidents based on check result
        
        Args:
            website_id (int): ID of the website
            is_up (bool): Whether the website is up
        """
        conn = self._get_connection()
        cursor = self._get_cursor()
        
        try:
            if not is_up:
                # Check if there's an existing unresolved incident
                cursor.execute('''
                SELECT id FROM incidents 
                WHERE website_id = ? AND resolved = 0
                ''', (website_id,))
                
                existing = cursor.fetchone()
                
                if not existing:
                    # Create new incident
                    cursor.execute('''
                    INSERT INTO incidents (website_id, start_time)
                    VALUES (?, ?)
                    ''', (website_id, datetime.now().isoformat()))
            else:
                # Check if there's an incident to resolve
                cursor.execute('''
                SELECT id, start_time FROM incidents 
                WHERE website_id = ? AND resolved = 0
                ''', (website_id,))
                
                incident = cursor.fetchone()
                
                if incident:
                    # Resolve the incident
                    now = datetime.now()
                    start_time = datetime.fromisoformat(incident['start_time'])
                    duration = int((now - start_time).total_seconds())
                    
                    cursor.execute('''
                    UPDATE incidents SET 
                        resolved = 1,
                        end_time = ?,
                        duration = ?
                    WHERE id = ?
                    ''', (now.isoformat(), duration, incident['id']))
            
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error updating incidents: {str(e)}")
            conn.rollback()
    
    def get_check_results(self, website_id, limit=100, offset=0):
        """
        Get check results for a website
        
        Args:
            website_id (int): ID of the website
            limit (int): Max number of results
            offset (int): Offset for pagination
            
        Returns:
            list: Check results
        """
        cursor = self._get_cursor()
        
        cursor.execute('''
        SELECT * FROM check_results
        WHERE website_id = ?
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
        ''', (website_id, limit, offset))
        
        results = []
        for row in cursor.fetchall():
            result = dict(row)
            # Parse JSON details if present
            if result.get('details'):
                try:
                    result['details'] = json.loads(result['details'])
                except:
                    pass
            results.append(result)
            
        return results
    
    def get_latest_check_result(self, website_id):
        """
        Get the latest check result for a website
        
        Args:
            website_id (int): ID of the website
            
        Returns:
            dict: Latest check result
        """
        cursor = self._get_cursor()
        
        cursor.execute('''
        SELECT * FROM check_results
        WHERE website_id = ?
        ORDER BY timestamp DESC
        LIMIT 1
        ''', (website_id,))
        
        row = cursor.fetchone()
        if row:
            result = dict(row)
            # Parse JSON details if present
            if result.get('details'):
                try:
                    result['details'] = json.loads(result['details'])
                except:
                    pass
            return result
        
        return None
    
    def get_uptime_percentage(self, website_id, days=30):
        """
        Calculate uptime percentage for a website
        
        Args:
            website_id (int): ID of the website
            days (int): Number of days to calculate for
            
        Returns:
            float: Uptime percentage
        """
        cursor = self._get_cursor()
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        cursor.execute('''
        SELECT COUNT(*) as total, 
               SUM(CASE WHEN is_up=1 THEN 1 ELSE 0 END) as up_count
        FROM check_results
        WHERE website_id = ? AND 
              datetime(timestamp) BETWEEN ? AND ?
        ''', (website_id, start_date.isoformat(), end_date.isoformat()))
        
        result = cursor.fetchone()
        
        if result and result['total'] > 0:
            return (result['up_count'] / result['total']) * 100
        
        return 100.0  # Default to 100% if no data
    
    def get_response_time_stats(self, website_id, days=30):
        """
        Get response time statistics for a website
        
        Args:
            website_id (int): ID of the website
            days (int): Number of days to calculate for
            
        Returns:
            dict: Response time statistics
        """
        cursor = self._get_cursor()
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        cursor.execute('''
        SELECT AVG(response_time) as avg_time,
               MIN(response_time) as min_time,
               MAX(response_time) as max_time
        FROM check_results
        WHERE website_id = ? AND 
              datetime(timestamp) BETWEEN ? AND ? AND
              is_up = 1
        ''', (website_id, start_date.isoformat(), end_date.isoformat()))
        
        result = cursor.fetchone()
        
        if result and result['avg_time'] is not None:
            return {
                'average': round(result['avg_time'], 2),
                'minimum': round(result['min_time'], 2),
                'maximum': round(result['max_time'], 2)
            }
        
        return {
            'average': 0,
            'minimum': 0,
            'maximum': 0
        }
    
    def get_incidents(self, website_id=None, limit=10, include_resolved=True):
        """
        Get incidents for websites
        
        Args:
            website_id (int, optional): ID of the website, or None for all
            limit (int): Max number of incidents
            include_resolved (bool): Include resolved incidents
            
        Returns:
            list: Incidents
        """
        cursor = self._get_cursor()
        
        query = '''
        SELECT i.*, w.name as website_name, w.url as website_url
        FROM incidents i
        JOIN websites w ON i.website_id = w.id
        '''
        
        params = []
        
        if website_id is not None:
            query += ' WHERE i.website_id = ?'
            params.append(website_id)
            
            if not include_resolved:
                query += ' AND i.resolved = 0'
        elif not include_resolved:
            query += ' WHERE i.resolved = 0'
            
        query += ' ORDER BY i.start_time DESC LIMIT ?'
        params.append(limit)
        
        cursor.execute(query, params)
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_daily_stats(self, website_id, days=30):
        """
        Get daily statistics for a website
        
        Args:
            website_id (int): ID of the website
            days (int): Number of days to calculate for
            
        Returns:
            list: Daily statistics
        """
        cursor = self._get_cursor()
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # SQLite date formatting
        cursor.execute('''
        SELECT 
            date(timestamp) as day,
            COUNT(*) as checks,
            SUM(CASE WHEN is_up=1 THEN 1 ELSE 0 END) as up_count,
            AVG(response_time) as avg_response_time,
            AVG(security_score) as avg_security_score
        FROM check_results
        WHERE website_id = ? AND 
              datetime(timestamp) BETWEEN ? AND ?
        GROUP BY date(timestamp)
        ORDER BY date(timestamp)
        ''', (website_id, start_date.isoformat(), end_date.isoformat()))
        
        results = []
        for row in cursor.fetchall():
            day_data = dict(row)
            # Calculate uptime percentage
            if day_data['checks'] > 0:
                day_data['uptime_percentage'] = (day_data['up_count'] / day_data['checks']) * 100
            else:
                day_data['uptime_percentage'] = 100.0
                
            # Round values
            if day_data['avg_response_time'] is not None:
                day_data['avg_response_time'] = round(day_data['avg_response_time'], 2)
            if day_data['avg_security_score'] is not None:
                day_data['avg_security_score'] = round(day_data['avg_security_score'], 2)
                
            results.append(day_data)
            
        return results