"""
Web dashboard for the Personal Domain Health Monitor
"""
import os
import json
import logging
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from wtforms import StringField, TextAreaField, BooleanField, SelectField, FieldList, EmailField
from wtforms.validators import DataRequired, URL, Email, Optional
from wtforms import StringField, IntegerField, PasswordField
logger = logging.getLogger(__name__)
from config import Config
def create_app(data_manager, website_manager, domain_monitor):
    """Create Flask app for the dashboard"""
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'your-secret-key'  # Change in production
    csrf = CSRFProtect(app)

    @app.template_filter('format_datetime')
    def format_datetime(value, format='%Y-%m-%d %H:%M:%S'):
        """Format a datetime string to a more readable format"""
        if not value:
            return ""
        try:
            # Try to parse the ISO format
            dt = datetime.fromisoformat(value)
            return dt.strftime(format)
        except (ValueError, TypeError):
            # Return original if parsing fails
            return value

    # Website form for adding/editing websites
    class WebsiteForm(FlaskForm):
        name = StringField('Name', validators=[DataRequired()])
        url = StringField('URL', validators=[DataRequired(), URL()])
        description = TextAreaField('Description')
        check_ssl = BooleanField('Check SSL Certificate', default=True)
        check_security = BooleanField('Perform Security Checks', default=True)
        alerts_enabled = BooleanField('Enable Alerts', default=True)
        alert_emails = TextAreaField('Alert Emails (one per line)')
        alert_phone = StringField('Alert Phone Number')
        # Add this right after your existing WebsiteForm class
    class ConfigForm(FlaskForm):
        # Database settings
        database_path = StringField('Database Path')

        # Monitor settings
        check_interval_minutes = IntegerField('Check Interval (minutes)')
        retry_attempts = IntegerField('Retry Attempts')
        connection_timeout = IntegerField('Connection Timeout (seconds)')

        # Email settings
        smtp_server = StringField('SMTP Server')
        smtp_port = IntegerField('SMTP Port')
        smtp_username = StringField('SMTP Username')
        smtp_password = PasswordField('SMTP Password')
        from_email = StringField('From Email')

        # Twilio settings
        twilio_account_sid = StringField('Twilio Account SID')
        twilio_auth_token = PasswordField('Twilio Auth Token')
        twilio_phone_number = StringField('Twilio Phone Number')
    @app.route('/')
    def index():
        """Dashboard home page"""
        websites = website_manager.get_all_websites()

        # Get latest status for each website
        for website in websites:
            latest_check = data_manager.get_latest_check_result(website['id'])
            if latest_check:
                website['status'] = 'Up' if latest_check['is_up'] else 'Down'
                website['latest_check'] = latest_check
            else:
                website['status'] = 'Unknown'
                website['latest_check'] = None

        # Get recent incidents
        incidents = data_manager.get_incidents(limit=5)

        return render_template('index.html',
                              websites=websites,
                              incidents=incidents)

    @app.route('/websites')
    def website_list():
        """List all websites"""
        websites = website_manager.get_all_websites()

        # Get latest status for each website
        for website in websites:
            latest_check = data_manager.get_latest_check_result(website['id'])
            if latest_check:
                website['status'] = 'Up' if latest_check['is_up'] else 'Down'
                website['latest_check'] = latest_check
            else:
                website['status'] = 'Unknown'
                website['latest_check'] = None

        return render_template('websites.html', websites=websites)

    @app.route('/websites/add', methods=['GET', 'POST'])
    def add_website():
        """Add a new website"""
        form = WebsiteForm()

        if form.validate_on_submit():
            # Process email list
            emails = []
            if form.alert_emails.data:
                emails = [email.strip() for email in form.alert_emails.data.split('\n') if email.strip()]

            # Add website
            website_id = website_manager.add_website(
                name=form.name.data,
                url=form.url.data,
                description=form.description.data,
                check_ssl=form.check_ssl.data,
                check_security=form.check_security.data,
                alerts_enabled=form.alerts_enabled.data,
                alert_emails=emails,
                alert_phone=form.alert_phone.data if form.alert_phone.data else None
            )

            if website_id:
                flash(f"Website '{form.name.data}' added successfully!", 'success')
                return redirect(url_for('website_detail', website_id=website_id))
            else:
                flash("Failed to add website. URL may already be monitored.", 'danger')

        return render_template('website_form.html', form=form, title="Add Website")

    @app.route('/websites/edit/<int:website_id>', methods=['GET', 'POST'])
    def edit_website(website_id):
        """Edit a website"""
        website = website_manager.get_website(website_id)
        if not website:
            flash("Website not found.", 'danger')
            return redirect(url_for('website_list'))

        form = WebsiteForm()

        if request.method == 'GET':
            # Fill form with existing data
            form.name.data = website['name']
            form.url.data = website['url']
            form.description.data = website['description']
            form.check_ssl.data = website['check_ssl']
            form.check_security.data = website['check_security']
            form.alerts_enabled.data = website['alerts_enabled']

            if website.get('alert_emails'):
                form.alert_emails.data = '\n'.join(website['alert_emails'])

            form.alert_phone.data = website.get('alert_phone', '')

        if form.validate_on_submit():
            # Process email list
            emails = []
            if form.alert_emails.data:
                emails = [email.strip() for email in form.alert_emails.data.split('\n') if email.strip()]

            # Update website
            success = website_manager.update_website(
                website_id=website_id,
                name=form.name.data,
                url=form.url.data,
                description=form.description.data,
                check_ssl=form.check_ssl.data,
                check_security=form.check_security.data,
                alerts_enabled=form.alerts_enabled.data,
                alert_emails=emails,
                alert_phone=form.alert_phone.data if form.alert_phone.data else None
            )

            if success:
                flash(f"Website '{form.name.data}' updated successfully!", 'success')
                return redirect(url_for('website_detail', website_id=website_id))
            else:
                flash("Failed to update website.", 'danger')

        return render_template('website_form.html', form=form,
                              title=f"Edit Website: {website['name']}")

    @app.route('/websites/delete/<int:website_id>', methods=['POST'])
    def delete_website(website_id):
        """Delete a website"""
        website = website_manager.get_website(website_id)
        if not website:
            flash("Website not found.", 'danger')
            return redirect(url_for('website_list'))

        if website_manager.delete_website(website_id):
            flash(f"Website '{website['name']}' deleted successfully!", 'success')
        else:
            flash("Failed to delete website.", 'danger')

        return redirect(url_for('website_list'))

    @app.route('/websites/<int:website_id>')
    def website_detail(website_id):
        """Website detail page"""
        website = website_manager.get_website(website_id)
        if not website:
            flash("Website not found.", 'danger')
            return redirect(url_for('website_list'))

        # Get website stats
        stats = website_manager.get_website_stats(website_id)

        # Get recent checks
        checks = data_manager.get_check_results(website_id, limit=20)

        # Get daily stats for graphs
        daily_stats = data_manager.get_daily_stats(website_id, days=30)

        # Prepare graph data
        uptime_data = []
        response_time_data = []

        for stat in daily_stats:
            day = stat['day']
            uptime_data.append({
                'day': day,
                'uptime': stat['uptime_percentage']
            })

            if stat['avg_response_time'] is not None:
                response_time_data.append({
                    'day': day,
                    'response_time': stat['avg_response_time']
                })

        # Convert to JSON for the template
        uptime_json = json.dumps(uptime_data)
        response_time_json = json.dumps(response_time_data)

        return render_template('website_detail.html',
                              website=website,
                              stats=stats,
                              checks=checks,
                              uptime_data=uptime_json,
                              response_time_data=response_time_json)





    @app.route('/api/recent-incidents', methods=['GET'])
    def api_recent_incidents():
        """API endpoint to get recent incidents"""
        limit = request.args.get('limit', 5, type=int)
        incidents = data_manager.get_incidents(limit=limit)

        return jsonify({
            'success': True,
            'incidents': incidents,
            'timestamp': datetime.now().isoformat()
        })
    @app.route('/api/websites/<int:website_id>/check', methods=['POST'])
    def api_check_website(website_id):
        """API endpoint to trigger a manual check"""
        website = website_manager.get_website(website_id)
        if not website:
            return jsonify({'error': 'Website not found'}), 404

        try:
            # Perform check
            result = domain_monitor.check_domain(
                website['url'],
                check_ssl=website.get('check_ssl', True),
                check_security=website.get('check_security', True)
            )

            # Store result
            data_manager.store_check_result(website_id, result)

            return jsonify({
                'success': True,
                'result': result
            })
        except Exception as e:
            logger.error(f"Error checking website: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/websites/<int:website_id>/ssl-info', methods=['GET'])
    def api_ssl_info(website_id):
        """API endpoint to get detailed SSL info"""
        website = website_manager.get_website(website_id)
        if not website:
            return jsonify({'error': 'Website not found'}), 404

        try:
            # Parse domain from URL
            from urllib.parse import urlparse
            domain = urlparse(website['url']).netloc

            # Get SSL info
            ssl_info = domain_monitor.get_ssl_info(domain)

            return jsonify({
                'success': True,
                'ssl_info': ssl_info
            })
        except Exception as e:
            logger.error(f"Error getting SSL info: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/websites/<int:website_id>/data', methods=['GET'])
    def api_website_data(website_id):
        """API endpoint to get website data for charts"""
        website = website_manager.get_website(website_id)
        if not website:
            return jsonify({'error': 'Website not found'}), 404

        # Get date range from query params
        days = request.args.get('days', 30, type=int)

        # Get daily stats
        daily_stats = data_manager.get_daily_stats(website_id, days=days)

        # Format data for charts
        chart_data = {
            'days': [stat['day'] for stat in daily_stats],
            'uptime': [stat['uptime_percentage'] for stat in daily_stats],
            'response_time': [stat['avg_response_time'] for stat in daily_stats],
            'security_score': [stat['avg_security_score'] for stat in daily_stats]
        }

        return jsonify({
            'success': True,
            'data': chart_data,
            'website': website['name']
        })

    @app.route('/incidents')
    def incidents():
        """Incidents page"""
        # Get all incidents with optional filtering
        website_id = request.args.get('website_id', type=int)
        resolved = request.args.get('resolved', '1')
        include_resolved = resolved != '0'

        incidents_list = data_manager.get_incidents(website_id=website_id, include_resolved=include_resolved)

        # Get all websites for the filter dropdown
        websites = website_manager.get_all_websites()

        return render_template('incidents.html',
                              incidents=incidents_list,
                              websites=websites,
                              selected_website=website_id,
                              include_resolved=include_resolved)



    @app.route('/api/website-status', methods=['GET'])
    def api_website_status():
        """API endpoint to get the latest status of all websites"""
        websites = website_manager.get_all_websites()

        # Get latest status for each website
        status_data = []
        for website in websites:
            latest_check = data_manager.get_latest_check_result(website['id'])
            status = {
                'id': website['id'],
                'name': website['name'],
                'status': 'Up' if latest_check and latest_check['is_up'] else 'Down' if latest_check else 'Unknown',
                'response_time': latest_check['response_time'] if latest_check and latest_check.get('response_time') else None,
                'last_checked': latest_check['timestamp'] if latest_check else None,
                'ssl_valid': latest_check['ssl_valid'] if latest_check and 'ssl_valid' in latest_check else None,
                'security_score': latest_check['security_score'] if latest_check and 'security_score' in latest_check else None
            }
            status_data.append(status)

        return jsonify({
            'status': status_data,
            'timestamp': datetime.now().isoformat()
        })

    @app.route('/api/last-check', methods=['GET'])
    def api_last_check():
        """API endpoint to get information about the last monitoring check"""
        try:
            if os.path.exists('last_check.json'):
                with open('last_check.json', 'r') as f:
                    last_check = json.load(f)
                    return jsonify({
                        'success': True,
                        'data': last_check
                    })
            else:
                return jsonify({
                    'success': False,
                    'error': 'No check data available'
                })
        except Exception as e:
            logger.error(f"Error retrieving last check data: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    @app.route('/settings', methods=['GET', 'POST'])
    def settings():
        """Application settings page"""
        config = Config()
        form = ConfigForm()

        if request.method == 'GET':
            # Fill form with current settings
            form.database_path.data = config.DATABASE_PATH
            form.check_interval_minutes.data = config.CHECK_INTERVAL_MINUTES
            form.retry_attempts.data = config.RETRY_ATTEMPTS
            form.connection_timeout.data = config.CONNECTION_TIMEOUT
            form.smtp_server.data = config.SMTP_SERVER
            form.smtp_port.data = config.SMTP_PORT
            form.smtp_username.data = config.SMTP_USERNAME
            # Don't fill password fields for security
            form.from_email.data = config.FROM_EMAIL
            form.twilio_account_sid.data = config.TWILIO_ACCOUNT_SID
            # Don't fill password fields for security
            form.twilio_phone_number.data = config.TWILIO_PHONE_NUMBER

        if form.validate_on_submit():
            try:
                # Create config dict
                config_data = {
                    'database_path': form.database_path.data,
                    'monitor_settings': {
                        'check_interval_minutes': form.check_interval_minutes.data,
                        'retry_attempts': form.retry_attempts.data,
                        'connection_timeout': form.connection_timeout.data
                    },
                    'email_settings': {
                        'smtp_server': form.smtp_server.data,
                        'smtp_port': form.smtp_port.data,
                        'smtp_username': form.smtp_username.data,
                        'from_email': form.from_email.data
                    },
                    'sms_settings': {
                        'twilio_account_sid': form.twilio_account_sid.data,
                        'twilio_phone_number': form.twilio_phone_number.data
                    },
                    'http_settings': {
                        'default_headers': config.DEFAULT_HTTP_HEADERS
                    }
                }

                # Only update passwords if provided
                if form.smtp_password.data:
                    config_data['email_settings']['smtp_password'] = form.smtp_password.data
                else:
                    config_data['email_settings']['smtp_password'] = config.SMTP_PASSWORD

                if form.twilio_auth_token.data:
                    config_data['sms_settings']['twilio_auth_token'] = form.twilio_auth_token.data
                else:
                    config_data['sms_settings']['twilio_auth_token'] = config.TWILIO_AUTH_TOKEN

                # Save config
                config.save_config(config_data)

                flash("Settings updated successfully. Restart the application for changes to take effect.", "success")
                return redirect(url_for('settings'))
            except Exception as e:
                logger.error(f"Error updating settings: {str(e)}")
                flash(f"Error updating settings: {str(e)}", "danger")

        return render_template('settings.html', form=form)
    # Create templates directory and templates
    @app.before_first_request
    def create_templates():
        import os
        templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
        if not os.path.exists(templates_dir):
            os.makedirs(templates_dir)

        # Create base template
        base_html = """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>{% block title %}Domain Health Monitor{% endblock %}</title>
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
                <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
                <style>
                    .status-up { color: #28a745; }
                    .status-down { color: #dc3545; }
                    .status-unknown { color: #6c757d; }
                </style>
                {% block head %}{% endblock %}
            </head>
            <body>
                <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
                    <div class="container">
                        <a class="navbar-brand" href="{{ url_for('index') }}">
                            <i class="bi bi-globe"></i> Domain Health Monitor
                        </a>
                        <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                            <span class="navbar-toggler-icon"></span>
                        </button>
                        <div class="collapse navbar-collapse" id="navbarNav">
                            <ul class="navbar-nav">
                                <li class="nav-item">
                                    <a class="nav-link" href="{{ url_for('index') }}">Dashboard</a>
                                </li>
                                <li class="nav-item">
                                    <a class="nav-link" href="{{ url_for('website_list') }}">Websites</a>
                                </li>
                                <li class="nav-item">
                                    <a class="nav-link" href="{{ url_for('incidents') }}">Incidents</a>
                                </li>
                                <li class="nav-item">
                                    <a class="nav-link" href="{{ url_for('settings') }}">Settings</a>
                                </li>
                            </ul>
                        </div>
                    </div>
                </nav>

                <div class="container mt-4">
                    {% for category, message in get_flashed_messages(with_categories=true) %}
                    <div class="alert alert-{{ category }} alert-dismissible fade show">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                    </div>
                    {% endfor %}

                    {% block content %}{% endblock %}
                </div>

                <footer class="mt-5 py-3 bg-light text-center">
                    <div class="container">
                        <p class="text-muted mb-0">Personal Domain Health Monitor</p>
                    </div>
                </footer>

                <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
                <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

                <!-- Auto-refresh functionality -->
                <script>
                document.addEventListener('DOMContentLoaded', function() {
                    const AUTO_REFRESH_INTERVAL = 60000; // 60 seconds fallback
                    const CHECK_COMPLETION_INTERVAL = 5000; // 5 seconds, to check if monitoring tasks completed

                    // Get stored last check timestamp from localStorage (if any)
                    let lastCheckTimestamp = localStorage.getItem('lastCheckTimestamp');
                    let lastUpdateTimestamp = new Date().toISOString();
                    let autoRefreshEnabled = true;

                    // Function to check if a new monitoring task has completed
                    function checkMonitoringCompletion() {
                        if (!autoRefreshEnabled) return;

                        fetch('/api/last-check')
                            .then(response => response.json())
                            .then(data => {
                                if (data.success && data.data && data.data.timestamp) {
                                    // Get stored last timestamp from localStorage
                                    let storedTimestamp = localStorage.getItem('lastCheckTimestamp');

                                    // If there's a new check result and it's newer than our last known check
                                    const newTimestamp = data.data.timestamp;
                                    if (!storedTimestamp || new Date(newTimestamp) > new Date(storedTimestamp)) {
                                        console.log(`New check detected: ${newTimestamp} (previous: ${storedTimestamp || 'none'})`);

                                        // Store the new timestamp
                                        localStorage.setItem('lastCheckTimestamp', newTimestamp);
                                        lastCheckTimestamp = newTimestamp;

                                        // Immediately fetch updated website status
                                        fetchWebsiteStatus(true);

                                        // Show a notification about the completed check
                                        showNotification(`Monitoring completed: ${data.data.websites_up} sites up, ${data.data.websites_down} sites down`);
                                    }
                                }
                            })
                            .catch(error => {
                                console.error('Error checking monitoring completion:', error);
                            })
                            .finally(() => {
                                if (autoRefreshEnabled) {
                                    setTimeout(checkMonitoringCompletion, CHECK_COMPLETION_INTERVAL);
                                }
                            });
                    }

                    // Function to fetch the latest website statuses
                    function fetchWebsiteStatus(skipScheduling = false) {
                        if (!autoRefreshEnabled && !skipScheduling) return;

                        fetch('/api/website-status')
                            .then(response => response.json())
                            .then(data => {
                                updateDashboard(data);
                                lastUpdateTimestamp = data.timestamp;
                            })
                            .catch(error => {
                                console.error('Error fetching website status:', error);
                            })
                            .finally(() => {
                                if (autoRefreshEnabled && !skipScheduling) {
                                    setTimeout(fetchWebsiteStatus, AUTO_REFRESH_INTERVAL);
                                }
                            });
                    }

                    // Function to show a notification to the user
                    function showNotification(message) {
                        // Create a notification container in the UI
                        const container = document.querySelector('.container');
                        if (container) {
                            const notification = document.createElement('div');
                            notification.className = 'alert alert-info alert-dismissible fade show';
                            notification.innerHTML = `
                                ${message}
                                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                            `;

                            // Insert at the top of the container
                            container.insertBefore(notification, container.firstChild);

                            // Auto-remove after 5 seconds
                            setTimeout(() => {
                                notification.classList.remove('show');
                                setTimeout(() => notification.remove(), 500);
                            }, 5000);
                        }
                    }

                    // Function to update dashboard elements with new data
                    function updateDashboard(data) {
                        // Only update if we're on a page that displays website statuses
                        if (document.querySelector('.website-status-table')) {
                            updateWebsiteStatusTable(data.status);
                        }

                        // Update the incidents list if we're on a page with incidents
                        if (document.querySelector('.incidents-list')) {
                            updateRecentIncidents();
                        }

                        // Update last refresh indicator
                        const lastRefreshEl = document.getElementById('last-refresh-time');
                        if (lastRefreshEl) {
                            const now = new Date();
                            lastRefreshEl.textContent = now.toLocaleTimeString();
                        }
                    }

                    // Function to fetch and update recent incidents
                    function updateRecentIncidents() {
                        fetch('/api/recent-incidents')
                            .then(response => response.json())
                            .then(data => {
                                if (data.success) {
                                    const incidentsList = document.querySelector('.incidents-list');
                                    if (!incidentsList || !data.incidents || data.incidents.length === 0) return;

                                    // Clear current incidents
                                    incidentsList.innerHTML = '';

                                    // Add new incidents
                                    data.incidents.forEach(incident => {
                                        const incidentItem = document.createElement('div');
                                        incidentItem.className = 'list-group-item';

                                        const header = document.createElement('div');
                                        header.className = 'd-flex justify-content-between';

                                        const title = document.createElement('h6');
                                        title.className = 'mb-1';
                                        title.textContent = incident.website_name;

                                        const statusBadge = document.createElement('span');
                                        statusBadge.className = incident.resolved ? 'badge bg-success' : 'badge bg-danger';
                                        statusBadge.textContent = incident.resolved ? 'Resolved' : 'Ongoing';

                                        header.appendChild(title);
                                        header.appendChild(statusBadge);
                                        incidentItem.appendChild(header);

                                        const startTime = document.createElement('p');
                                        startTime.className = 'mb-1';
                                        startTime.textContent = `Started: ${formatDateTime(incident.start_time)}`;
                                        incidentItem.appendChild(startTime);

                                        if (incident.resolved) {
                                            const duration = document.createElement('p');
                                            duration.className = 'mb-1';
                                            duration.textContent = `Duration: ${formatDuration(incident.duration)}`;
                                            incidentItem.appendChild(duration);
                                        }

                                        incidentsList.appendChild(incidentItem);
                                    });
                                }
                            })
                            .catch(error => {
                                console.error('Error updating incidents:', error);
                            });
                    }

                    // Helper function to format date time
                    function formatDateTime(timestamp) {
                        if (!timestamp) return '';
                        const date = new Date(timestamp);
                        return date.toLocaleString();
                    }

                    // Helper function to format duration
                    function formatDuration(seconds) {
                        if (!seconds) return '';

                        if (seconds < 60) {
                            return `${seconds} seconds`;
                        } else if (seconds < 3600) {
                            const minutes = Math.floor(seconds / 60);
                            return `${minutes} minutes`;
                        } else {
                            const hours = Math.floor(seconds / 3600);
                            const minutes = Math.floor((seconds % 3600) / 60);
                            return `${hours} hours, ${minutes} minutes`;
                        }
                    }

                    // Function to update the website status table
                    function updateWebsiteStatusTable(statusData) {
                        const table = document.querySelector('.website-status-table tbody');
                        if (!table) return;

                        // Loop through each row in the table and update with new data
                        const rows = table.querySelectorAll('tr');
                        rows.forEach(row => {
                            const websiteId = row.getAttribute('data-website-id');
                            if (!websiteId) return;

                            // Find matching website data
                            const websiteData = statusData.find(site => site.id == websiteId);
                            if (!websiteData) return;

                            // Update status cell
                            const statusCell = row.querySelector('.status-cell');
                            if (statusCell) {
                                let statusHTML = '';
                                if (websiteData.status === 'Up') {
                                    statusHTML = '<span class="badge bg-success">Up</span>';
                                } else if (websiteData.status === 'Down') {
                                    statusHTML = '<span class="badge bg-danger">Down</span>';
                                } else {
                                    statusHTML = '<span class="badge bg-secondary">Unknown</span>';
                                }
                                statusCell.innerHTML = statusHTML;
                            }

                            // Update response time cell
                            const responseTimeCell = row.querySelector('.response-time-cell');
                            if (responseTimeCell) {
                                responseTimeCell.textContent = websiteData.response_time ? `${websiteData.response_time} ms` : '-';
                            }

                            // Update last checked cell
                            const lastCheckedCell = row.querySelector('.last-checked-cell');
                            if (lastCheckedCell && websiteData.last_checked) {
                                const date = new Date(websiteData.last_checked);
                                lastCheckedCell.textContent = date.toLocaleString();
                            }

                            // Update SSL cell if present
                            const sslCell = row.querySelector('.ssl-cell');
                            if (sslCell && websiteData.ssl_valid !== null) {
                                let sslHTML = '';
                                if (websiteData.ssl_valid === 1 || websiteData.ssl_valid === true) {
                                    sslHTML = '<span class="badge bg-success">Valid</span>';
                                } else if (websiteData.ssl_valid === 0 || websiteData.ssl_valid === false) {
                                    sslHTML = '<span class="badge bg-danger">Invalid</span>';
                                } else {
                                    sslHTML = '<span class="badge bg-secondary">Unknown</span>';
                                }
                                sslCell.innerHTML = sslHTML;
                            }

                            // Update security score cell if present
                            const securityCell = row.querySelector('.security-cell');
                            if (securityCell && websiteData.security_score !== null) {
                                let scoreHTML = '';
                                const score = websiteData.security_score;
                                if (score >= 80) {
                                    scoreHTML = `<span class="badge bg-success">${score}%</span>`;
                                } else if (score >= 50) {
                                    scoreHTML = `<span class="badge bg-warning text-dark">${score}%</span>`;
                                } else {
                                    scoreHTML = `<span class="badge bg-danger">${score}%</span>`;
                                }
                                securityCell.innerHTML = scoreHTML;
                            }
                        });
                    }

                    // Add indicator to the navbar showing when the page was last refreshed
                    function addRefreshIndicator() {
                        const navbarNav = document.querySelector('#navbarNav');
                        if (!navbarNav) return;

                        const refreshContainer = document.createElement('div');
                        refreshContainer.className = 'ms-auto d-flex align-items-center';

                        const refreshIndicator = document.createElement('div');
                        refreshIndicator.className = 'refresh-indicator text-light me-3';
                        refreshIndicator.innerHTML = `
                            <small>Last updated: <span id="last-refresh-time">${new Date().toLocaleTimeString()}</span></small>
                            <button id="toggle-refresh" class="btn btn-sm btn-outline-light ms-2">
                                <i class="bi bi-arrow-repeat"></i>
                            </button>
                        `;

                        refreshContainer.appendChild(refreshIndicator);
                        navbarNav.appendChild(refreshContainer);

                        // Add toggle functionality
                        document.getElementById('toggle-refresh').addEventListener('click', function() {
                            autoRefreshEnabled = !autoRefreshEnabled;
                            this.classList.toggle('btn-outline-light', autoRefreshEnabled);
                            this.classList.toggle('btn-outline-danger', !autoRefreshEnabled);

                            if (autoRefreshEnabled) {
                                fetchWebsiteStatus(); // Start polling again
                                checkMonitoringCompletion();
                            }
                        });
                    }

                    // Add data-website-id attributes to rows in the table for easier updates
                    function prepareWebsiteTables() {
                        const tables = document.querySelectorAll('.website-status-table');
                        tables.forEach(table => {
                            const rows = table.querySelectorAll('tbody tr');
                            rows.forEach(row => {
                                // Check if row already has website-id
                                if (row.hasAttribute('data-website-id')) return;

                                // Extract website ID from the detail link
                                const detailLink = row.querySelector('a[href*="website_detail"]');
                                if (detailLink) {
                                    const href = detailLink.getAttribute('href');
                                    const websiteId = href.match(/website_detail\/(\d+)/)?.[1] ||
                                                     href.match(/website_id=(\d+)/)?.[1];
                                    if (websiteId) {
                                        row.setAttribute('data-website-id', websiteId);
                                    }
                                }

                                // Add classes to cells for easier targeting
                                const cells = row.querySelectorAll('td');
                                if (cells.length >= 3) { // Make sure there are enough cells
                                    // Assuming standard layout: Name, URL, Status, Response Time, Last Checked, etc.
                                    cells[2].classList.add('status-cell');
                                    if (cells.length > 3) cells[3].classList.add('response-time-cell');
                                    if (cells.length > 4) cells[4].classList.add('last-checked-cell');
                                    if (cells.length > 5) cells[5].classList.add('ssl-cell');
                                    if (cells.length > 6) cells[6].classList.add('security-cell');
                                }
                            });

                            // Mark table for auto-refresh
                            table.classList.add('website-status-table');
                        });
                    }

                    // Initialize
                    addRefreshIndicator();
                    prepareWebsiteTables();
                    setTimeout(fetchWebsiteStatus, 5000); // Initial delay before first refresh
                    setTimeout(checkMonitoringCompletion, 2000); // Start checking for monitor task completions
                });
                </script>

                {% block scripts %}{% endblock %}
            </body>
            </html>
        """

        # Create index template
        index_html = """
        {% extends "base.html" %}

        {% block title %}Dashboard - Domain Health Monitor{% endblock %}

        {% block content %}
        <h1 class="mb-4">Dashboard</h1>

        <div class="row">
            <div class="col-md-8">
                <div class="card mb-4">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h5 class="mb-0">Websites Status</h5>
                        <a href="{{ url_for('website_list') }}" class="btn btn-sm btn-primary">View All</a>
                    </div>
                    <div class="card-body">
                        {% if websites %}
                            <div class="table-responsive">
                                <table class="table table-striped table-hover website-status-table">
                                    <thead>
                                        <tr>
                                            <th>Name</th>
                                            <th>URL</th>
                                            <th>Status</th>
                                            <th>Response Time</th>
                                            <th>Last Checked</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {% for website in websites %}
                                        <tr data-website-id="{{ website.id }}">
                                            <td>
                                                <a href="{{ url_for('website_detail', website_id=website.id) }}">
                                                    {{ website.name }}
                                                </a>
                                            </td>
                                            <td>
                                                <a href="{{ website.url }}" target="_blank">
                                                    {{ website.url }}
                                                </a>
                                            </td>
                                            <td class="status-cell">
                                                {% if website.status == 'Up' %}
                                                    <span class="badge bg-success">Up</span>
                                                {% elif website.status == 'Down' %}
                                                    <span class="badge bg-danger">Down</span>
                                                {% else %}
                                                    <span class="badge bg-secondary">Unknown</span>
                                                {% endif %}
                                            </td>
                                            <td class="response-time-cell">
                                                {% if website.latest_check and website.latest_check.response_time %}
                                                    {{ website.latest_check.response_time }} ms
                                                {% else %}
                                                    -
                                                {% endif %}
                                            </td>
                                            <td class="last-checked-cell">
                                                {% if website.latest_check %}
                                                    {{ website.latest_check.timestamp|format_datetime }}
                                                {% else %}
                                                    Never
                                                {% endif %}
                                            </td>
                                        </tr>
                                        {% endfor %}
                                    </tbody>
                                </table>
                            </div>
                        {% else %}
                            <div class="alert alert-info mb-0">
                                No websites are being monitored.
                                <a href="{{ url_for('add_website') }}" class="alert-link">Add your first website</a>
                            </div>
                        {% endif %}
                    </div>
                </div>
            </div>

            <div class="col-md-4">
                <div class="card mb-4">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h5 class="mb-0">Recent Incidents</h5>
                        <a href="{{ url_for('incidents') }}" class="btn btn-sm btn-primary">View All</a>
                    </div>
                    <div class="card-body">
                        {% if incidents %}
                            <div class="list-group incidents-list">
                                {% for incident in incidents %}
                                <div class="list-group-item">
                                    <div class="d-flex justify-content-between">
                                        <h6 class="mb-1">{{ incident.website_name }}</h6>
                                        {% if incident.resolved %}
                                            <span class="badge bg-success">Resolved</span>
                                        {% else %}
                                            <span class="badge bg-danger">Ongoing</span>
                                        {% endif %}
                                    </div>
                                    <p class="mb-1">Started: {{ incident.start_time|format_datetime }}</p>
                                    {% if incident.resolved %}
                                        <p class="mb-1">Duration:
                                            {% if incident.duration < 60 %}
                                                {{ incident.duration }} seconds
                                            {% elif incident.duration < 3600 %}
                                                {{ (incident.duration // 60) }} minutes
                                            {% else %}
                                                {{ (incident.duration // 3600) }} hours, {{ ((incident.duration % 3600) // 60) }} minutes
                                            {% endif %}
                                        </p>
                                    {% endif %}
                                </div>
                                {% endfor %}
                            </div>
                        {% else %}
                            <div class="alert alert-info mb-0">
                                No incidents recorded yet.
                            </div>
                        {% endif %}
                    </div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0">Quick Actions</h5>
                    </div>
                    <div class="card-body">
                        <div class="d-grid gap-2">
                            <a href="{{ url_for('add_website') }}" class="btn btn-primary">
                                <i class="bi bi-plus-circle"></i> Add Website
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        {% endblock %}
        """

        # Create websites list template
        websites_html = """
            {% extends "base.html" %}

            {% block title %}Websites - Domain Health Monitor{% endblock %}

            {% block content %}
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h1>Websites</h1>
                <a href="{{ url_for('add_website') }}" class="btn btn-primary">
                    <i class="bi bi-plus-circle"></i> Add Website
                </a>
            </div>

            {% if websites %}
                <div class="card">
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table table-striped table-hover website-status-table">
                                <thead>
                                    <tr>
                                        <th>Name</th>
                                        <th>URL</th>
                                        <th>Status</th>
                                        <th>Response Time</th>
                                        <th>SSL</th>
                                        <th>Security</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for website in websites %}
                                    <tr data-website-id="{{ website.id }}">
                                        <td>
                                            <a href="{{ url_for('website_detail', website_id=website.id) }}">
                                                {{ website.name }}
                                            </a>
                                        </td>
                                        <td>
                                            <a href="{{ website.url }}" target="_blank">
                                                {{ website.url }}
                                            </a>
                                        </td>
                                        <td class="status-cell">
                                            {% if website.status == 'Up' %}
                                                <span class="badge bg-success">Up</span>
                                            {% elif website.status == 'Down' %}
                                                <span class="badge bg-danger">Down</span>
                                            {% else %}
                                                <span class="badge bg-secondary">Unknown</span>
                                            {% endif %}
                                        </td>
                                        <td class="response-time-cell">
                                            {% if website.latest_check and website.latest_check.response_time %}
                                                {{ website.latest_check.response_time }} ms
                                            {% else %}
                                                -
                                            {% endif %}
                                        </td>
                                        <td class="ssl-cell">
                                            {% if website.latest_check and website.latest_check.ssl_valid == 1 %}
                                                <span class="badge bg-success">Valid</span>
                                            {% elif website.latest_check and website.latest_check.ssl_valid == 0 %}
                                                <span class="badge bg-danger">Invalid</span>
                                            {% else %}
                                                <span class="badge bg-secondary">Unknown</span>
                                            {% endif %}
                                        </td>
                                        <td class="security-cell">
                                            {% if website.latest_check and website.latest_check.security_score %}
                                                {% if website.latest_check.security_score >= 80 %}
                                                    <span class="badge bg-success">{{ website.latest_check.security_score }}%</span>
                                                {% elif website.latest_check.security_score >= 50 %}
                                                    <span class="badge bg-warning text-dark">{{ website.latest_check.security_score }}%</span>
                                                {% else %}
                                                    <span class="badge bg-danger">{{ website.latest_check.security_score }}%</span>
                                                {% endif %}
                                            {% else %}
                                                <span class="badge bg-secondary">Unknown</span>
                                            {% endif %}
                                        </td>
                                        <td>
                                            <div class="btn-group">
                                                <a href="{{ url_for('website_detail', website_id=website.id) }}" class="btn btn-sm btn-outline-primary">
                                                    <i class="bi bi-eye"></i>
                                                </a>
                                                <a href="{{ url_for('edit_website', website_id=website.id) }}" class="btn btn-sm btn-outline-secondary">
                                                    <i class="bi bi-pencil"></i>
                                                </a>
                                                <button type="button" class="btn btn-sm btn-outline-danger"
                                                        data-bs-toggle="modal" data-bs-target="#deleteModal{{ website.id }}">
                                                    <i class="bi bi-trash"></i>
                                                </button>
                                            </div>

                                            <!-- Delete Confirmation Modal -->
                                            <div class="modal fade" id="deleteModal{{ website.id }}" tabindex="-1">
                                                <div class="modal-dialog">
                                                    <div class="modal-content">
                                                        <div class="modal-header">
                                                            <h5 class="modal-title">Confirm Delete</h5>
                                                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                                        </div>
                                                        <div class="modal-body">
                                                            <p>Are you sure you want to delete <strong>{{ website.name }}</strong>?</p>
                                                            <p class="text-danger">This will delete all monitoring data and cannot be undone.</p>
                                                        </div>
                                                        <div class="modal-footer">
                                                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                                                            <form action="{{ url_for('delete_website', website_id=website.id) }}" method="post">
                                                                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                                                                <button type="submit" class="btn btn-danger">Delete</button>
                                                            </form>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            {% else %}
                <div class="alert alert-info">
                    No websites are being monitored.
                    <a href="{{ url_for('add_website') }}" class="alert-link">Add your first website</a>
                </div>
            {% endif %}
            {% endblock %}
        """

        # Create website form template
        website_form_html = """
        {% extends "base.html" %}

        {% block title %}{{ title }} - Domain Health Monitor{% endblock %}

        {% block content %}
        <h1 class="mb-4">{{ title }}</h1>

        <div class="card">
            <div class="card-body">
                <form method="post">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

                    <div class="mb-3">
                        <label for="name" class="form-label">Name</label>
                        <input type="text" class="form-control {% if form.name.errors %}is-invalid{% endif %}"
                               id="name" name="name" value="{{ form.name.data or '' }}" required>
                        {% if form.name.errors %}
                            <div class="invalid-feedback">
                                {% for error in form.name.errors %}
                                    {{ error }}
                                {% endfor %}
                            </div>
                        {% endif %}
                    </div>

                    <div class="mb-3">
                        <label for="url" class="form-label">URL</label>
                        <input type="url" class="form-control {% if form.url.errors %}is-invalid{% endif %}"
                               id="url" name="url" value="{{ form.url.data or '' }}"
                               placeholder="https://example.com" required>
                        {% if form.url.errors %}
                            <div class="invalid-feedback">
                                {% for error in form.url.errors %}
                                    {{ error }}
                                {% endfor %}
                            </div>
                        {% endif %}
                        <small class="form-text text-muted">
                            Enter the full URL including http:// or https://
                        </small>
                    </div>

                    <div class="mb-3">
                        <label for="description" class="form-label">Description (Optional)</label>
                        <textarea class="form-control" id="description" name="description" rows="2">{{ form.description.data or '' }}</textarea>
                    </div>

                    <div class="row mb-3">
                        <div class="col-md-4">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="check_ssl" name="check_ssl"
                                       {% if form.check_ssl.data or form.check_ssl.data is none %}checked{% endif %}>
                                <label class="form-check-label" for="check_ssl">
                                    Check SSL Certificate
                                </label>
                            </div>
                        </div>

                        <div class="col-md-4">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="check_security" name="check_security"
                                       {% if form.check_security.data or form.check_security.data is none %}checked{% endif %}>
                                <label class="form-check-label" for="check_security">
                                    Perform Security Checks
                                </label>
                            </div>
                        </div>

                        <div class="col-md-4">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="alerts_enabled" name="alerts_enabled"
                                       {% if form.alerts_enabled.data or form.alerts_enabled.data is none %}checked{% endif %}>
                                <label class="form-check-label" for="alerts_enabled">
                                    Enable Alerts
                                </label>
                            </div>
                        </div>
                    </div>

<div class="mb-3">
                        <label for="alert_emails" class="form-label">Alert Emails (Optional)</label>
                        <textarea class="form-control" id="alert_emails" name="alert_emails"
                                  rows="3" placeholder="Enter one email per line">{{ form.alert_emails.data or '' }}</textarea>
                    </div>

                    <div class="mb-3">
                        <label for="alert_phone" class="form-label">Alert Phone Number (Optional)</label>
                        <input type="text" class="form-control" id="alert_phone" name="alert_phone"
                               value="{{ form.alert_phone.data or '' }}" placeholder="+1234567890">
                        <small class="form-text text-muted">
                            Include country code (e.g., +1 for US)
                        </small>
                    </div>

                    <div class="d-flex justify-content-between">
                        <a href="{{ url_for('website_list') }}" class="btn btn-secondary">Cancel</a>
                        <button type="submit" class="btn btn-primary">Save</button>
                    </div>
                </form>
            </div>
        </div>
        {% endblock %}
        """

        # Create website detail template
        website_detail_html = """
        {% extends "base.html" %}

        {% block title %}{{ website.name }} - Domain Health Monitor{% endblock %}

        {% block head %}
        <style>
            .card-metric {
                text-align: center;
                padding: 1rem;
            }
            .metric-value {
                font-size: 2rem;
                font-weight: bold;
            }
            .metric-label {
                font-size: 0.9rem;
                color: #6c757d;
            }
        </style>
        <meta name="website-id" content="{{ website.id }}">
        {% endblock %}

        {% block content %}
        <div class="d-flex justify-content-between align-items-center mb-4">
            <h1>{{ website.name }}</h1>
            <div class="btn-group">
                <button id="checkNowBtn" class="btn btn-primary">
                    <i class="bi bi-arrow-repeat"></i> Check Now
                </button>
                <a href="{{ url_for('edit_website', website_id=website.id) }}" class="btn btn-secondary">
                    <i class="bi bi-pencil"></i> Edit
                </a>
            </div>
        </div>

        <div class="row mb-4">
            <div class="col-md-6">
                <div class="card h-100">
                    <div class="card-header">
                        <h5 class="mb-0">Website Information</h5>
                    </div>
                    <div class="card-body">
                        <dl class="row mb-0">
                            <dt class="col-sm-4">URL</dt>
                            <dd class="col-sm-8">
                                <a href="{{ website.url }}" target="_blank">{{ website.url }}</a>
                            </dd>

                            <dt class="col-sm-4">Description</dt>
                            <dd class="col-sm-8">{{ website.description or 'N/A' }}</dd>

                            <dt class="col-sm-4">Current Status</dt>
                            <dd class="col-sm-8">
                                {% if stats.latest_check and stats.latest_check.is_up %}
                                    <span class="badge bg-success">Up</span>
                                {% elif stats.latest_check and not stats.latest_check.is_up %}
                                    <span class="badge bg-danger">Down</span>
                                {% else %}
                                    <span class="badge bg-secondary">Unknown</span>
                                {% endif %}
                            </dd>

                            <dt class="col-sm-4">Monitoring Settings</dt>
                            <dd class="col-sm-8">
                                {% if website.check_ssl %}
                                    <span class="badge bg-info">SSL Checks</span>
                                {% endif %}
                                {% if website.check_security %}
                                    <span class="badge bg-info">Security Checks</span>
                                {% endif %}
                                {% if website.alerts_enabled %}
                                    <span class="badge bg-info">Alerts Enabled</span>
                                {% endif %}
                            </dd>

                            <dt class="col-sm-4">Last Checked</dt>
                            <dd class="col-sm-8">
                                {% if stats.latest_check %}
                                    {{ stats.latest_check.timestamp|format_datetime }}
                                {% else %}
                                    Never
                                {% endif %}
                            </dd>
                        </dl>
                    </div>
                </div>
            </div>

            <div class="col-md-6">
                <div class="card h-100">
                    <div class="card-header">
                        <h5 class="mb-0">Performance Metrics</h5>
                    </div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-sm-6">
                                <div class="card-metric">
                                    <div class="metric-value text-success">{{ stats.uptime['30d'] }}%</div>
                                    <div class="metric-label">30-Day Uptime</div>
                                </div>
                            </div>
                            <div class="col-sm-6">
                                <div class="card-metric">
                                    <div class="metric-value text-success">{{ stats.uptime['7d'] }}%</div>
                                    <div class="metric-label">7-Day Uptime</div>
                                </div>
                            </div>
                            <div class="col-sm-6">
                                <div class="card-metric">
                                    <div class="metric-value">{{ stats.response_time.average }} ms</div>
                                    <div class="metric-label">Avg Response Time</div>
                                </div>
                            </div>
                            <div class="col-sm-6">
                                <div class="card-metric">
                                    {% if stats.latest_check and stats.latest_check.ssl_days_remaining %}
                                        <div class="metric-value {% if stats.latest_check.ssl_days_remaining > 30 %}text-success{% elif stats.latest_check.ssl_days_remaining > 7 %}text-warning{% else %}text-danger{% endif %}">
                                            {{ stats.latest_check.ssl_days_remaining }} days
                                        </div>
                                        <div class="metric-label">SSL Expiry</div>
                                    {% elif stats.latest_check and stats.latest_check.ssl_valid is not none %}
                                        <div class="metric-value text-danger">Invalid</div>
                                        <div class="metric-label">SSL Certificate</div>
                                    {% else %}
                                        <div class="metric-value text-secondary">N/A</div>
                                        <div class="metric-label">SSL Status</div>
                                    {% endif %}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="row mb-4">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0">Performance History</h5>
                    </div>
                    <div class="card-body">
                        <ul class="nav nav-tabs" id="myTab" role="tablist">
                            <li class="nav-item" role="presentation">
                                <button class="nav-link active" id="uptime-tab" data-bs-toggle="tab" data-bs-target="#uptime"
                                        type="button" role="tab" aria-selected="true">Uptime</button>
                            </li>
                            <li class="nav-item" role="presentation">
                                <button class="nav-link" id="response-tab" data-bs-toggle="tab" data-bs-target="#response"
                                        type="button" role="tab" aria-selected="false">Response Time</button>
                            </li>
                        </ul>
                        <div class="tab-content pt-3">
                            <div class="tab-pane fade show active" id="uptime" role="tabpanel">
                                <canvas id="uptimeChart" height="250"></canvas>
                            </div>
                            <div class="tab-pane fade" id="response" role="tabpanel">
                                <canvas id="responseTimeChart" height="250"></canvas>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="row">
            <div class="col-md-6">
                <div class="card mb-4">
                    <div class="card-header">
                        <h5 class="mb-0">Recent Checks</h5>
                    </div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table table-sm">
                                <thead>
                                    <tr>
                                        <th>Time</th>
                                        <th>Status</th>
                                        <th>Response</th>
                                        <th>Code</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for check in checks %}
                                    <tr>
                                        <td>{{ check.timestamp|format_datetime }}</td>
                                        <td>
                                            {% if check.is_up %}
                                                <span class="badge bg-success">Up</span>
                                            {% else %}
                                                <span class="badge bg-danger">Down</span>
                                            {% endif %}
                                        </td>
                                        <td>{{ check.response_time if check.response_time else '-' }} ms</td>
                                        <td>{{ check.status_code if check.status_code else '-' }}</td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>

            <div class="col-md-6">
                <div class="card mb-4">
                    <div class="card-header">
                        <h5 class="mb-0">Recent Incidents</h5>
                    </div>
                    <div class="card-body">
                        {% if stats.incidents %}
                            <div class="list-group">
                                {% for incident in stats.incidents %}
                                <div class="list-group-item">
                                    <div class="d-flex justify-content-between">
                                        <h6 class="mb-1">{{ incident.start_time|format_datetime }}</h6>
                                        {% if incident.resolved %}
                                            <span class="badge bg-success">Resolved</span>
                                        {% else %}
                                            <span class="badge bg-danger">Ongoing</span>
                                        {% endif %}
                                    </div>
                                    {% if incident.resolved %}
                                        <p class="mb-1">
                                            Duration:
                                            {% if incident.duration < 60 %}
                                                {{ incident.duration }} seconds
                                            {% elif incident.duration < 3600 %}
                                                {{ (incident.duration // 60) }} minutes
                                            {% else %}
                                                {{ (incident.duration // 3600) }} hours, {{ ((incident.duration % 3600) // 60) }} minutes
                                            {% endif %}
                                        </p>
                                    {% endif %}
                                </div>
                                {% endfor %}
                            </div>
                        {% else %}
                            <div class="alert alert-info mb-0">
                                No incidents recorded for this website.
                            </div>
                        {% endif %}
                    </div>
                </div>

                {% if stats.latest_check and stats.latest_check.security_score is not none %}
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0">Security Assessment</h5>
                    </div>
                    <div class="card-body">
                        <div class="text-center mb-3">
                            <div class="display-4
                                {% if stats.latest_check.security_score >= 80 %}text-success
                                {% elif stats.latest_check.security_score >= 50 %}text-warning
                                {% else %}text-danger{% endif %}">
                                {{ stats.latest_check.security_score }}%
                            </div>
                            <p class="text-muted">Security Score</p>
                        </div>

                        {% if stats.latest_check.details and stats.latest_check.details.security_issues %}
                            <h6>Security Issues:</h6>
                            <ul class="list-group">
                                {% for issue in stats.latest_check.details.security_issues %}
                                <li class="list-group-item">{{ issue }}</li>
                                {% endfor %}
                            </ul>
                        {% endif %}
                    </div>
                </div>
                {% endif %}
            </div>
        </div>
        {% endblock %}

        {% block scripts %}

        <script>
        document.addEventListener('DOMContentLoaded', function() {
            const CHECK_COMPLETION_INTERVAL = 5000; // 5 seconds
            let autoRefreshEnabled = true;
            const websiteId = document.querySelector('meta[name="website-id"]')?.getAttribute('content');

            if (!websiteId) return; // Exit if we can't determine website ID

            // Function to check if monitoring completed and update if needed
            function checkMonitoringCompletion() {
                if (!autoRefreshEnabled || !websiteId) return;

                fetch('/api/last-check')
                    .then(response => response.json())
                    .then(data => {
                        if (data.success && data.data && data.data.timestamp) {
                            // If there's a new check, refresh the website data
                            fetchWebsiteData();
                        }
                    })
                    .catch(error => {
                        console.error('Error checking monitoring completion:', error);
                    })
                    .finally(() => {
                        if (autoRefreshEnabled) {
                            setTimeout(checkMonitoringCompletion, CHECK_COMPLETION_INTERVAL);
                        }
                    });
            }

            // Function to fetch the latest data for this specific website
            function fetchWebsiteData() {
                fetch(`/api/websites/${websiteId}/data?days=30`)
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            updateDetailPage(data.data);
                        }
                    })
                    .catch(error => {
                        console.error('Error fetching website detail:', error);
                    });
            }

            // Function to update the website detail page charts
            function updateDetailPage(data) {
                // Update charts
                if (window.uptimeChart && data.uptime) {
                    window.uptimeChart.data.labels = data.days;
                    window.uptimeChart.data.datasets[0].data = data.uptime;
                    window.uptimeChart.update();
                }

                if (window.responseChart && data.response_time) {
                    window.responseChart.data.labels = data.days;
                    window.responseChart.data.datasets[0].data = data.response_time;
                    window.responseChart.update();
                }

                // Update current status
                updateStatus();
            }

            // Function to update status, response time, etc.
            function updateStatus() {
                fetch(`/api/website-status`)
                    .then(response => response.json())
                    .then(data => {
                        const website = data.status.find(site => site.id == websiteId);
                        if (website) {
                            // Update status badge
                            const statusEl = document.querySelector('.current-status');
                            if (statusEl) {
                                if (website.status === 'Up') {
                                    statusEl.innerHTML = '<span class="badge bg-success">Up</span>';
                                } else if (website.status === 'Down') {
                                    statusEl.innerHTML = '<span class="badge bg-danger">Down</span>';
                                } else {
                                    statusEl.innerHTML = '<span class="badge bg-secondary">Unknown</span>';
                                }
                            }

                            // Update response time if present
                            const respTimeEl = document.querySelector('.current-response-time');
                            if (respTimeEl && website.response_time) {
                                respTimeEl.textContent = `${website.response_time} ms`;
                            }

                            // Add refresh notification
                            const refreshMsg = document.createElement('div');
                            refreshMsg.className = 'text-muted small mt-2';
                            refreshMsg.textContent = `Updated: ${new Date().toLocaleTimeString()}`;

                            // Replace old notification if exists
                            const oldNotification = document.querySelector('.refresh-notification');
                            if (oldNotification) {
                                oldNotification.remove();
                            }

                            refreshMsg.classList.add('refresh-notification');

                            // Find a good place to insert the notification
                            const metricsCard = document.querySelector('.performance-metrics');
                            if (metricsCard) {
                                metricsCard.appendChild(refreshMsg);
                            }
                        }
                    })
                    .catch(error => {
                        console.error('Error updating status:', error);
                    });
            }

            // Expose charts globally for updates
            function exposeChartsGlobally() {
                setTimeout(() => {
                    const allCharts = Chart.instances || [];
                    for (let i = 0; i < allCharts.length; i++) {
                        const chart = allCharts[i];
                        if (chart.canvas.id === 'uptimeChart') {
                            window.uptimeChart = chart;
                        } else if (chart.canvas.id === 'responseTimeChart') {
                            window.responseChart = chart;
                        }
                    }
                }, 1000); // Give charts time to initialize
            }

            // Initialize
            exposeChartsGlobally();

            // Add class to metrics card for easier targeting
            const metricsCard = document.querySelector('.card:has(h5:contains("Performance Metrics"))');
            if (metricsCard) {
                metricsCard.classList.add('performance-metrics');
            }

            // Modify the DOM to allow for status updates
            const statusElement = document.querySelector('dd:contains("Up"), dd:contains("Down"), dd:contains("Unknown")');
            if (statusElement) {
                statusElement.classList.add('current-status');
            }

            const respTimeElement = document.querySelector('dd:contains("ms")');
            if (respTimeElement) {
                respTimeElement.classList.add('current-response-time');
            }

            // Start monitoring for updates
            setTimeout(checkMonitoringCompletion, 2000);
        });
        </script>


        <script>
            // Chart data
            const uptimeData = {{ uptime_data|safe }};
            const responseTimeData = {{ response_time_data|safe }};

            // Create charts when the DOM is ready
            document.addEventListener('DOMContentLoaded', function() {
                // Uptime chart
                const uptimeCtx = document.getElementById('uptimeChart').getContext('2d');
                const uptimeChart = new Chart(uptimeCtx, {
                    type: 'line',
                    data: {
                        labels: uptimeData.map(d => d.day),
                        datasets: [{
                            label: 'Uptime %',
                            data: uptimeData.map(d => d.uptime),
                            backgroundColor: 'rgba(40, 167, 69, 0.2)',
                            borderColor: 'rgba(40, 167, 69, 1)',
                            borderWidth: 2,
                            tension: 0.1,
                            fill: true
                        }]
                    },
                    options: {
                        scales: {
                            y: {
                                beginAtZero: false,
                                min: Math.max(0, Math.min(...uptimeData.map(d => d.uptime)) - 5),
                                max: 100,
                                title: {
                                    display: true,
                                    text: 'Uptime %'
                                }
                            },
                            x: {
                                title: {
                                    display: true,
                                    text: 'Date'
                                }
                            }
                        },
                        plugins: {
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        return `Uptime: ${context.parsed.y.toFixed(2)}%`;
                                    }
                                }
                            }
                        }
                    }
                });

                // Response time chart
                const responseCtx = document.getElementById('responseTimeChart').getContext('2d');
                const responseChart = new Chart(responseCtx, {
                    type: 'line',
                    data: {
                        labels: responseTimeData.map(d => d.day),
                        datasets: [{
                            label: 'Response Time (ms)',
                            data: responseTimeData.map(d => d.response_time),
                            backgroundColor: 'rgba(0, 123, 255, 0.2)',
                            borderColor: 'rgba(0, 123, 255, 1)',
                            borderWidth: 2,
                            tension: 0.1,
                            fill: true
                        }]
                    },
                    options: {
                        scales: {
                            y: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: 'Response Time (ms)'
                                }
                            },
                            x: {
                                title: {
                                    display: true,
                                    text: 'Date'
                                }
                            }
                        },
                        plugins: {
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        return `Response Time: ${context.parsed.y.toFixed(1)} ms`;
                                    }
                                }
                            }
                        }
                    }
                });

                // Handle "Check Now" button
                document.getElementById('checkNowBtn').addEventListener('click', function() {
                    this.disabled = true;
                    this.innerHTML = '<i class="bi bi-hourglass-split"></i> Checking...';

                    // Call the API to perform a check
                    fetch('{{ url_for("api_check_website", website_id=website.id) }}', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': '{{ csrf_token() }}'
                        }
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            alert('Check completed successfully!');
                            location.reload();
                        } else {
                            alert('Error: ' + data.error);
                            this.disabled = false;
                            this.innerHTML = '<i class="bi bi-arrow-repeat"></i> Check Now';
                        }
                    })
                    .catch(error => {
                        alert('Error: ' + error);
                        this.disabled = false;
                        this.innerHTML = '<i class="bi bi-arrow-repeat"></i> Check Now';
                    });
                });
            });


        </script>
        {% endblock %}
        """

        # Create incidents template
        incidents_html = """
        {% extends "base.html" %}

        {% block title %}Incidents - Domain Health Monitor{% endblock %}

        {% block content %}
        <h1 class="mb-4">Incidents</h1>

        <div class="card mb-4">
            <div class="card-header">
                <h5 class="mb-0">Filter Incidents</h5>
            </div>
            <div class="card-body">
                <form method="get" class="row g-3">
                    <div class="col-md-5">
                        <label for="website_id" class="form-label">Website</label>
                        <select class="form-select" id="website_id" name="website_id">
                            <option value="">All Websites</option>
                            {% for website in websites %}
                                <option value="{{ website.id }}" {% if selected_website == website.id %}selected{% endif %}>
                                    {{ website.name }}
                                </option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="col-md-5">
                        <label for="resolved" class="form-label">Status</label>
                        <select class="form-select" id="resolved" name="resolved">
                            <option value="1" {% if include_resolved %}selected{% endif %}>All Incidents</option>
                            <option value="0" {% if not include_resolved %}selected{% endif %}>Ongoing Only</option>
                        </select>
                    </div>
                    <div class="col-md-2 d-flex align-items-end">
                        <button type="submit" class="btn btn-primary w-100">Apply Filters</button>
                    </div>
                </form>
            </div>
        </div>

        {% if incidents %}
            <div class="table-responsive incidents-list">
                <table class="table table-striped">
                    <thead>
                        <tr>
                            <th>Website</th>
                            <th>Start Time</th>
                            <th>End Time</th>
                            <th>Duration</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for incident in incidents %}
                        <tr>
                            <td>
                                <a href="{{ url_for('website_detail', website_id=incident.website_id) }}">
                                    {{ incident.website_name }}
                                </a>
                            </td>
                            <td>{{ incident.start_time|format_datetime }}</td>
                            <td>{{ incident.end_time|format_datetime if incident.end_time else 'Ongoing' }}</td>
                            <td>
                                {% if incident.duration %}
                                    {% if incident.duration < 60 %}
                                        {{ incident.duration }} seconds
                                    {% elif incident.duration < 3600 %}
                                        {{ (incident.duration // 60) }} minutes
                                    {% else %}
                                        {{ (incident.duration // 3600) }} hours, {{ ((incident.duration % 3600) // 60) }} minutes
                                    {% endif %}
                                {% else %}
                                    Ongoing
                                {% endif %}
                            </td>
                            <td>
                                {% if incident.resolved %}
                                    <span class="badge bg-success">Resolved</span>
                                {% else %}
                                    <span class="badge bg-danger">Ongoing</span>
                                {% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        {% else %}
            <div class="alert alert-info">
                No incidents found with the current filters.
            </div>
        {% endif %}
        {% endblock %}
        """
        # Add this template string before the templates dictionary
        settings_html = """
        {% extends "base.html" %}

        {% block title %}Settings - Domain Health Monitor{% endblock %}

        {% block content %}
        <h1 class="mb-4">Application Settings</h1>

        <div class="card mb-4">
            <div class="card-body">
                <form method="post">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

                    <h5 class="mb-3">Database Settings</h5>
                    <div class="mb-3">
                        <label for="database_path" class="form-label">Database Path</label>
                        <input type="text" class="form-control" id="database_path" name="database_path" value="{{ form.database_path.data or '' }}">
                        <small class="text-muted">Path to SQLite database file</small>
                    </div>

                    <hr class="my-4">

                    <h5 class="mb-3">Monitor Settings</h5>
                    <div class="row mb-3">
                        <div class="col-md-4">
                            <label for="check_interval_minutes" class="form-label">Check Interval (minutes)</label>
                            <input type="number" class="form-control" id="check_interval_minutes" name="check_interval_minutes" value="{{ form.check_interval_minutes.data or 5 }}">
                        </div>
                        <div class="col-md-4">
                            <label for="retry_attempts" class="form-label">Retry Attempts</label>
                            <input type="number" class="form-control" id="retry_attempts" name="retry_attempts" value="{{ form.retry_attempts.data or 2 }}">
                        </div>
                        <div class="col-md-4">
                            <label for="connection_timeout" class="form-label">Connection Timeout (seconds)</label>
                            <input type="number" class="form-control" id="connection_timeout" name="connection_timeout" value="{{ form.connection_timeout.data or 10 }}">
                        </div>
                    </div>

                    <hr class="my-4">

                    <h5 class="mb-3">Email Alert Settings</h5>
                    <div class="mb-3">
                        <label for="smtp_server" class="form-label">SMTP Server</label>
                        <input type="text" class="form-control" id="smtp_server" name="smtp_server" value="{{ form.smtp_server.data or '' }}">
                    </div>
                    <div class="row mb-3">
                        <div class="col-md-4">
                            <label for="smtp_port" class="form-label">SMTP Port</label>
                            <input type="number" class="form-control" id="smtp_port" name="smtp_port" value="{{ form.smtp_port.data or 587 }}">
                        </div>
                        <div class="col-md-8">
                            <label for="from_email" class="form-label">From Email</label>
                            <input type="email" class="form-control" id="from_email" name="from_email" value="{{ form.from_email.data or '' }}">
                        </div>
                    </div>
                    <div class="row mb-3">
                        <div class="col-md-6">
                            <label for="smtp_username" class="form-label">SMTP Username</label>
                            <input type="text" class="form-control" id="smtp_username" name="smtp_username" value="{{ form.smtp_username.data or '' }}">
                        </div>
                        <div class="col-md-6">
                            <label for="smtp_password" class="form-label">SMTP Password</label>
                            <input type="password" class="form-control" id="smtp_password" name="smtp_password" placeholder="Leave blank to keep current password">
                        </div>
                    </div>

                    <hr class="my-4">

                    <h5 class="mb-3">SMS Alert Settings (Twilio)</h5>
                    <div class="mb-3">
                        <label for="twilio_account_sid" class="form-label">Account SID</label>
                        <input type="text" class="form-control" id="twilio_account_sid" name="twilio_account_sid" value="{{ form.twilio_account_sid.data or '' }}">
                    </div>
                    <div class="row mb-3">
                        <div class="col-md-6">
                            <label for="twilio_auth_token" class="form-label">Auth Token</label>
                            <input type="password" class="form-control" id="twilio_auth_token" name="twilio_auth_token" placeholder="Leave blank to keep current token">
                        </div>
                        <div class="col-md-6">
                            <label for="twilio_phone_number" class="form-label">Twilio Phone Number</label>
                            <input type="text" class="form-control" id="twilio_phone_number" name="twilio_phone_number" value="{{ form.twilio_phone_number.data or '' }}" placeholder="+1234567890">
                        </div>
                    </div>

                    <div class="d-grid gap-2 mt-4">
                        <button type="submit" class="btn btn-primary">Save Settings</button>
                    </div>

                    <div class="alert alert-warning mt-4">
                        <strong>Note:</strong> Application restart required for changes to take effect.
                    </div>
                </form>
            </div>
        </div>
        {% endblock %}
        """
        # Write templates to files
        # Add this to the templates dictionary in create_templates
        templates = {
            'base.html': base_html,
            'index.html': index_html,
            'websites.html': websites_html,
            'website_form.html': website_form_html,
            'website_detail.html': website_detail_html,
            'incidents.html': incidents_html,
            'settings.html': settings_html  # Add this line
        }

        for name, content in templates.items():
            template_path = os.path.join(templates_dir, name)
            with open(template_path, 'w') as f:
                f.write(content)

        logger.info(f"Created templates in {templates_dir}")

    return app
