#!/usr/bin/env python3
"""
Web interface for Email Finder
"""
import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from wtforms import StringField, SubmitField, BooleanField
from wtforms.validators import DataRequired
from email_finder import EmailFinder

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
csrf = CSRFProtect(app)

class EmailFinderForm(FlaskForm):
    """Form for Email Finder input"""
    first_name = StringField('First Name', validators=[DataRequired()])
    last_name = StringField('Last Name', validators=[DataRequired()])
    company = StringField('Company', validators=[DataRequired()])
    additional_domains = StringField('Additional Domains (comma separated)')
    headless = BooleanField('Run in Headless Mode', default=True)
    submit = SubmitField('Find Emails')

@app.route('/', methods=['GET', 'POST'])
def index():
    """Main route for the application"""
    form = EmailFinderForm()
    results = None
    profile_info = None
    
    if form.validate_on_submit():
        first_name = form.first_name.data
        last_name = form.last_name.data
        company = form.company.data
        headless = form.headless.data
        
        # Process additional domains
        additional_domains = []
        if form.additional_domains.data:
            additional_domains = [domain.strip() for domain in form.additional_domains.data.split(',')]
        
        # Initialize the email finder
        finder = EmailFinder(headless=headless)
        
        try:
            # Extract profile info first
            profile_info = finder.extract_profile_info(first_name, last_name, company)
            
            if not profile_info:
                flash('Could not process profile information. Please check the inputs and try again.', 'danger')
                return render_template('index.html', form=form)
            
            # Find emails
            results = finder.find_emails(first_name, last_name, company, additional_domains)
            
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
        finally:
            finder.cleanup()
    
    return render_template('index.html', form=form, results=results, profile_info=profile_info)

@app.route('/api/find-emails', methods=['POST'])
def api_find_emails():
    """API endpoint for finding emails"""
    data = request.json
    
    if not data or 'first_name' not in data or 'last_name' not in data or 'company' not in data:
        return jsonify({'error': 'First name, last name, and company are required'}), 400
    
    first_name = data['first_name']
    last_name = data['last_name']
    company = data['company']
    additional_domains = data.get('additional_domains', [])
    headless = data.get('headless', True)
    
    finder = EmailFinder(headless=headless)
    
    try:
        # Extract profile info
        profile_info = finder.extract_profile_info(first_name, last_name, company)
        
        if not profile_info:
            return jsonify({'error': 'Could not process profile information'}), 404
        
        # Find emails
        results = finder.find_emails(first_name, last_name, company, additional_domains)
        
        return jsonify({
            'profile': profile_info,
            'emails': results
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        finder.cleanup()

if __name__ == '__main__':
    app.run(debug=True)
