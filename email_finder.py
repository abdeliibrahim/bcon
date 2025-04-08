#!/usr/bin/env python3
"""
Email Finder - A tool to find work emails using first name, last name, and company domain
"""
import os
import re
import time
import random
import argparse
import validators
import json
import requests
from urllib.parse import urlparse, quote_plus
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# Load environment variables
load_dotenv()

class EmailFinder:
    """Main class for finding emails based on name and company information"""
    
    # Default configuration
    DEFAULT_CONFIG = {
        "user_agents": [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36"
        ],
        "email_formats": {
            "firstinitiallastname@": ["flast@", "first initial last name", "first initial followed by last name"],
            "firstname.lastname@": ["first.last@", "first dot last", "firstname dot lastname"],
            "firstname@": ["first@", "firstname only"],
            "firstinitial.lastname@": ["f.last@", "first initial dot last name"],
            "firstnamelastname@": ["firstlast@", "firstname lastname", "first last"],
            "firstname_lastname@": ["first_last@", "firstname underscore lastname"],
            "lastname.firstname@": ["last.first@", "lastname dot firstname"],
            "lastnameonly@": ["last@", "lastname only"]
        },
        "default_email_format": "firstname.lastname@",
        "delays": {
            "between_requests": [1.0, 3.0],  # Random delay between min and max seconds
            "after_captcha": [5.0, 10.0]     # Longer delay after handling CAPTCHA
        },
        "retries": {
            "max_attempts": 3,
            "backoff_factor": 2.0
        },
        "google_search": {
            "api_key": os.getenv("GOOGLE_API_KEY", ""),
            "search_engine_id": os.getenv("GOOGLE_SEARCH_ENGINE_ID", ""),
            "results_per_page": 10
        }
    }
    
    def __init__(self, headless: bool = True, config_path: str = None, api_key: str = None, search_engine_id: str = None):
        """Initialize the Email Finder
        
        Args:
            headless: Whether to run the browser in headless mode
            config_path: Path to configuration file (JSON)
            api_key: Google Custom Search API key (overrides env variable and config)
            search_engine_id: Google Custom Search Engine ID (overrides env variable and config)
        """
        # Load configuration
        self.config = self.DEFAULT_CONFIG.copy()
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    user_config = json.load(f)
                    self.config.update(user_config)
            except Exception as e:
                print(f"{Fore.YELLOW}[!] Error loading config file: {str(e)}, using defaults{Style.RESET_ALL}")
        
        # Override API key and search engine ID if provided
        if api_key:
            self.config["google_search"]["api_key"] = api_key
        if search_engine_id:
            self.config["google_search"]["search_engine_id"] = search_engine_id
            
        # Check if API key is available
        if not self.config["google_search"]["api_key"]:
            print(f"{Fore.YELLOW}[!] Google API key not found. Set GOOGLE_API_KEY environment variable or provide it as a parameter.{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}[!] Falling back to Selenium-based search.{Style.RESET_ALL}")
        
        # Initialize Selenium WebDriver settings (as fallback)
        self.headless = headless
        self.driver = None
        
        # We'll still keep a requests session for API calls and simple operations
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': random.choice(self.config['user_agents']),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.google.com/'
        })
        
    def _initialize_driver(self):
        """Initialize the Selenium WebDriver (used as fallback)"""
        if self.driver is not None:
            return
            
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless=new")
        
        # Set a random user agent
        chrome_options.add_argument(f"user-agent={random.choice(self.config['user_agents'])}")
        
        # Add standard options
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-extensions")
        
        try:
            # Try using the system Chrome directly
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.set_page_load_timeout(30)  # Set page load timeout
        except Exception as e:
            print(f"Error initializing Chrome directly: {e}")
            raise RuntimeError(f"Failed to initialize Chrome: {e}")
    
    def _close_driver(self):
        """Close the Selenium WebDriver"""
        if self.driver is not None:
            self.driver.quit()
            self.driver = None
    
    def _random_delay(self, delay_type="between_requests"):
        """Add a random delay to avoid rate limiting
        
        Args:
            delay_type: Type of delay from config
        """
        min_delay, max_delay = self.config["delays"][delay_type]
        time.sleep(random.uniform(min_delay, max_delay))
    
    def _google_custom_search(self, query: str, page: int = 1) -> Dict[str, Any]:
        """Perform a Google Custom Search using the API
        
        Args:
            query: Search query
            page: Page number (1-based)
            
        Returns:
            Dict containing search results or None if API key is not available
        """
        api_key = self.config["google_search"]["api_key"]
        search_engine_id = self.config["google_search"]["search_engine_id"]
        
        if not api_key:
            print(f"{Fore.YELLOW}[!] Google API key not available. Cannot perform Custom Search.{Style.RESET_ALL}")
            return None
            
        if not search_engine_id:
            # If search engine ID is not provided, use a default that searches the entire web
            print(f"{Fore.YELLOW}[!] Search Engine ID not provided. Using default web search.{Style.RESET_ALL}")
        
        try:
            # Calculate start index (1-based)
            start = (page - 1) * self.config["google_search"]["results_per_page"] + 1
            
            # Construct the API URL
            url = f"https://www.googleapis.com/customsearch/v1"
            params = {
                "key": api_key,
                "cx": search_engine_id,
                "q": query,
                "start": start,
                "num": self.config["google_search"]["results_per_page"]
            }
            
            print(f"{Fore.BLUE}[*] Performing Google Custom Search for: {query}{Style.RESET_ALL}")
            
            # Make the API request
            response = self.session.get(url, params=params)
            
            # Check if the request was successful
            if response.status_code == 200:
                return response.json()
            else:
                print(f"{Fore.RED}[!] Google Custom Search API returned status code {response.status_code}{Style.RESET_ALL}")
                print(f"{Fore.RED}[!] Response: {response.text}{Style.RESET_ALL}")
                return None
                
        except Exception as e:
            print(f"{Fore.RED}[!] Error performing Google Custom Search: {str(e)}{Style.RESET_ALL}")
            return None
    
    def extract_profile_info(self, first_name: str, last_name: str, company: str) -> Dict[str, Any]:
        """Extract profile information from provided name and company
        
        Args:
            first_name: First name of the person
            last_name: Last name of the person
            company: Company name
            
        Returns:
            Dict containing profile information
        """
        print(f"{Fore.BLUE}[*] Processing information for {first_name} {last_name} at {company}...{Style.RESET_ALL}")
        
        try:
            profile_info = {}
            
            # Store the provided information
            profile_info['name'] = f"{first_name} {last_name}"
            profile_info['first_name'] = first_name
            profile_info['last_name'] = last_name
            profile_info['company'] = company
            
            # Attempt to determine company domain
            company_domain = self.get_company_domain(company)
            profile_info['company_domain'] = company_domain
            
            return profile_info
            
        except Exception as e:
            print(f"{Fore.RED}[!] Error processing profile information: {str(e)}{Style.RESET_ALL}")
            return {}
    
    def get_company_domain(self, company_name: str) -> Optional[str]:
        """Get the domain for a company using Google Custom Search API
        
        Args:
            company_name: Name of the company
            
        Returns:
            Company domain or None if not found
        """
        print(f"{Fore.BLUE}[*] Looking up domain for {company_name}...{Style.RESET_ALL}")
        
        try:
            # Clean company name for search
            clean_company = company_name.lower().strip()
            
            # Try direct approach first - assume company.com
            domain = f"{clean_company.replace(' ', '')}.com"
            
            # Check if domain exists using DNS lookup
            try:
                response = requests.get(f"https://dns.google/resolve?name={domain}&type=A", timeout=5)
                dns_data = response.json()
                if dns_data.get('Answer'):
                    return domain
            except Exception:
                pass
            
            # If direct approach fails, try Google Custom Search API
            search_query = f"{clean_company} official website"
            
            # Try the API search first
            search_results = self._google_custom_search(search_query)
            
            if search_results and 'items' in search_results:
                # Extract domains from the search results
                for item in search_results['items'][:3]:  # Check top 3 results
                    url = item.get('link')
                    if url:
                        parsed_url = urlparse(url)
                        if parsed_url.netloc and '.' in parsed_url.netloc:
                            domain = parsed_url.netloc
                            if domain.startswith('www.'):
                                domain = domain[4:]
                            return domain
            
            # If no domain found, return a default based on company name
            return f"{clean_company.replace(' ', '')}.com"
            
        except Exception as e:
            print(f"{Fore.RED}[!] Error finding company domain: {str(e)}{Style.RESET_ALL}")
            return f"{company_name.lower().replace(' ', '')}.com"
    
    def find_email_format(self, company_domain: str) -> Optional[str]:
        """Find the email format used by a company through Google Custom Search API
        
        Args:
            company_domain: Domain of the company
            
        Returns:
            Email format pattern or None if not found
        """
        print(f"{Fore.BLUE}[*] Searching for email format for {company_domain}...{Style.RESET_ALL}")
        
        try:
            # Extract company name from domain
            company_name = company_domain.split('.')[0]
            
            # Get common formats from config
            common_formats = self.config["email_formats"]
            
            # Use a more specific search query that's likely to find email format results
            search_query = f"{company_name} email format pattern typically follows"
            
            # Try the API search first
            search_results = self._google_custom_search(search_query)
            
            if search_results and 'items' in search_results:
                # Extract snippets from the search results
                snippets = []
                
                for item in search_results['items']:
                    # Get the snippet
                    snippet = item.get('snippet', '')
                    if snippet and len(snippet.strip()) > 20:  # Ignore very short snippets
                        snippets.append(snippet.lower())
                        print(f"[+] Found snippet: {snippet[:100]}...")
                
                # Look for patterns in snippets
                for snippet in snippets:
                    # Check for the typical format description
                    if "email format" in snippet or "email pattern" in snippet:
                        # Try to extract the pattern from the snippet
                        for format_name, patterns in common_formats.items():
                            for pattern in patterns:
                                if pattern in snippet:
                                    print(f"{Fore.GREEN}[+] Found email format: {format_name}{Style.RESET_ALL}")
                                    return format_name
                        
                        # If we found the typical phrase but couldn't identify the pattern,
                        # check for percentage mentions which often indicate the format
                        if "%" in snippet:
                            for format_name, patterns in common_formats.items():
                                for pattern in patterns:
                                    if pattern in snippet and re.search(r'\d{2}%', snippet):
                                        print(f"{Fore.GREEN}[+] Found email format with percentage: {format_name}{Style.RESET_ALL}")
                                        return format_name
            
            # Try a second search with a different query
            search_query2 = f"{company_name} company email format"
            search_results2 = self._google_custom_search(search_query2)
            
            if search_results2 and 'items' in search_results2:
                # Extract snippets from the search results
                snippets = []
                
                for item in search_results2['items']:
                    # Get the snippet
                    snippet = item.get('snippet', '')
                    if snippet and len(snippet.strip()) > 20:  # Ignore very short snippets
                        snippets.append(snippet.lower())
                
                # Look for patterns in snippets
                for snippet in snippets:
                    for format_name, patterns in common_formats.items():
                        for pattern in patterns:
                            if pattern in snippet:
                                print(f"{Fore.GREEN}[+] Found email format from second search: {format_name}{Style.RESET_ALL}")
                                return format_name
            
            # Since we couldn't find a specific format through searches,
            # try multiple common formats for all companies
            # This approach is more generic and avoids hardcoding company-specific logic
            common_formats_to_try = [
                'firstinitiallastname@',  # jsmith@company.com
                'firstname.lastname@',    # john.smith@company.com
                'firstname@',             # john@company.com
                'firstnamelastname@',     # johnsmith@company.com
                'firstname_lastname@'     # john_smith@company.com
            ]
            
            # Return a list of formats to try instead of just one
            print(f"{Fore.GREEN}[+] Using multiple common email formats for all searches{Style.RESET_ALL}")
            return common_formats_to_try
            
            # We won't reach this code since we're now always returning multiple formats
            # but keeping it as a fallback just in case
            default_format = self.config["default_email_format"]
            print(f"{Fore.YELLOW}[!] No specific email format found, using default format: {default_format}{Style.RESET_ALL}")
            return default_format
            
        except Exception as e:
            print(f"{Fore.RED}[!] Error finding email format: {str(e)}{Style.RESET_ALL}")
            # Return the default format from config
            return self.config["default_email_format"]
    
    def generate_email_patterns(self, profile_info: Dict[str, Any], domains: List[str] = None) -> List[str]:
        """Generate possible email patterns based on profile information
        
        Args:
            profile_info: Dictionary containing profile information
            domains: List of domains to generate emails for
            
        Returns:
            List of possible email addresses
        """
        if not profile_info.get('name'):
            return []
            
        # Get name components
        first_name = profile_info.get('first_name', '').lower()
        last_name = profile_info.get('last_name', '').lower()
        
        if not first_name or not last_name:
            # Split the name into first and last name if not provided separately
            name_parts = profile_info['name'].split()
            if len(name_parts) < 2:
                return []
                
            first_name = name_parts[0].lower()
            last_name = name_parts[-1].lower()
        
        # Initialize patterns list
        patterns = []
        
        # Use company domain if available, otherwise use provided domains
        if profile_info.get('company_domain'):
            company_domain = profile_info['company_domain']
            
            # Try to find the email format used by the company
            email_format = self.find_email_format(company_domain)
            
            # Handle the case where multiple formats are returned (for specific companies)
            if isinstance(email_format, list):
                for format_type in email_format:
                    if format_type == 'firstname@':
                        patterns.append(f"{first_name}@{company_domain}")
                    elif format_type == 'firstname.lastname@':
                        patterns.append(f"{first_name}.{last_name}@{company_domain}")
                    elif format_type == 'firstinitial.lastname@' or format_type == 'f.lastname@':
                        patterns.append(f"{first_name[0]}.{last_name}@{company_domain}")
                    elif format_type == 'firstnamelastname@':
                        patterns.append(f"{first_name}{last_name}@{company_domain}")
                    elif format_type == 'firstname_lastname@':
                        patterns.append(f"{first_name}_{last_name}@{company_domain}")
                    elif format_type == 'firstinitiallastname@':
                        patterns.append(f"{first_name[0]}{last_name}@{company_domain}")
                    elif format_type == 'lastname.firstname@':
                        patterns.append(f"{last_name}.{first_name}@{company_domain}")
                    elif format_type == 'lastnameonly@':
                        patterns.append(f"{last_name}@{company_domain}")
            # Handle single format case
            elif email_format:
                if email_format == 'firstname@':
                    patterns.append(f"{first_name}@{company_domain}")
                elif email_format == 'firstname.lastname@':
                    patterns.append(f"{first_name}.{last_name}@{company_domain}")
                elif email_format == 'firstinitial.lastname@' or email_format == 'f.lastname@':
                    patterns.append(f"{first_name[0]}.{last_name}@{company_domain}")
                elif email_format == 'firstnamelastname@':
                    patterns.append(f"{first_name}{last_name}@{company_domain}")
                elif email_format == 'firstname_lastname@':
                    patterns.append(f"{first_name}_{last_name}@{company_domain}")
                elif email_format == 'firstinitiallastname@':
                    patterns.append(f"{first_name[0]}{last_name}@{company_domain}")
                elif email_format == 'lastname.firstname@':
                    patterns.append(f"{last_name}.{first_name}@{company_domain}")
                elif email_format == 'lastnameonly@':
                    patterns.append(f"{last_name}@{company_domain}")
                else:
                    # Default to common patterns if format not recognized
                    company_patterns = [
                        f"{first_name[0]}{last_name}@{company_domain}",  # FLast@domain pattern
                        f"{first_name}@{company_domain}",
                        f"{first_name}.{last_name}@{company_domain}",
                        f"{first_name}_{last_name}@{company_domain}",
                        f"{first_name}{last_name}@{company_domain}",
                        f"{first_name[0]}.{last_name}@{company_domain}",
                    ]
                    patterns.extend(company_patterns)
            else:
                # Use common patterns if no specific format found
                company_patterns = [
                    f"{first_name[0]}{last_name}@{company_domain}",  # FLast@domain pattern
                    f"{first_name}@{company_domain}",
                    f"{first_name}.{last_name}@{company_domain}",
                    f"{first_name}_{last_name}@{company_domain}",
                    f"{first_name}{last_name}@{company_domain}",
                    f"{first_name[0]}.{last_name}@{company_domain}",
                ]
                patterns.extend(company_patterns)
        
        # Add additional domains if provided
        if domains:
            for domain in domains:
                domain_patterns = [
                    f"{first_name[0]}{last_name}@{domain}",  # FLast@domain pattern
                    f"{first_name}@{domain}",
                    f"{last_name}@{domain}",
                    f"{first_name}.{last_name}@{domain}",
                    f"{first_name}_{last_name}@{domain}",
                    f"{first_name}{last_name}@{domain}",
                    f"{first_name[0]}.{last_name}@{domain}",
                ]
                patterns.extend(domain_patterns)
        
        return patterns
    
    def verify_email(self, email: str) -> Tuple[bool, Optional[str]]:
        """Verify if an email exists using various methods
        
        Args:
            email: Email address to verify
            
        Returns:
            Tuple of (is_valid, confidence)
        """
        # Method 1: Check email format
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return False, "Invalid format"
        
        # Method 2: Check if domain has MX records
        domain = email.split('@')[1]
        try:
            response = requests.get(f"https://dns.google/resolve?name={domain}&type=MX", timeout=5)
            mx_data = response.json()
            if not mx_data.get('Answer'):
                return False, "No MX records"
        except Exception:
            pass  # Continue with other methods
        
        # Method 3: Use SMTP verification without sending an email
        try:
            import socket
            import smtplib
            
            # Get the MX record
            mx_domain = None
            try:
                response = requests.get(f"https://dns.google/resolve?name={domain}&type=MX", timeout=5)
                mx_data = response.json()
                if mx_data.get('Answer'):
                    # Extract the MX domain from the first record
                    mx_record = mx_data['Answer'][0]['data']
                    # MX record format is "priority domain", so split and get the domain part
                    mx_domain = mx_record.split(' ')[1].rstrip('.')
            except Exception as e:
                print(f"Error getting MX record: {e}")
                mx_domain = domain  # Fallback to the email domain
            
            if not mx_domain:
                return False, "No MX domain"
            
            # Connect to the SMTP server
            smtp = smtplib.SMTP(timeout=10)
            smtp.set_debuglevel(0)  # Set to 1 for debugging
            
            # Connect to the MX server
            try:
                smtp.connect(mx_domain, 25)
            except (socket.gaierror, socket.timeout, ConnectionRefusedError):
                # If connecting to MX fails, try the domain itself
                try:
                    smtp.connect(domain, 25)
                except Exception:
                    return False, "Connection failed"
            
            # Say hello to the server
            try:
                smtp.helo()
            except Exception:
                smtp.quit()
                return False, "HELO failed"
            
            # Start TLS if supported
            try:
                if smtp.has_extn('starttls'):
                    smtp.starttls()
                    smtp.helo()
            except Exception:
                pass  # Continue without TLS
            
            # Set the sender and recipient
            sender = f"verify@{domain}"  # Use the same domain
            
            # MAIL FROM
            try:
                smtp.mail(sender)
            except Exception:
                smtp.quit()
                return False, "MAIL FROM failed"
            
            # RCPT TO - this checks if the recipient exists
            try:
                code, message = smtp.rcpt(email)
                smtp.quit()
                
                # Check the response code
                if code == 250:
                    return True, "High"  # Email exists
                elif code == 550:
                    return False, "Invalid"  # Email doesn't exist
                else:
                    return True, "Medium"  # Uncertain
            except Exception:
                smtp.quit()
                return True, "Low"  # Assume it might be valid
                
        except Exception as e:
            print(f"Error in SMTP verification: {e}")
            pass  # Continue with other methods
        
        # For fallback, we'll return a "possible" result
        return True, "Medium"
    
    def find_emails(self, first_name: str, last_name: str, company: str, additional_domains: List[str] = None) -> List[Dict[str, Any]]:
        """Find emails for a person based on their name and company
        
        Args:
            first_name: First name of the person
            last_name: Last name of the person
            company: Company name
            additional_domains: Additional domains to check
            
        Returns:
            List of dictionaries containing email information
        """
        # Extract profile information
        profile_info = self.extract_profile_info(first_name, last_name, company)
        if not profile_info:
            print(f"{Fore.RED}[!] Could not process profile information{Style.RESET_ALL}")
            return []
        
        print(f"{Fore.GREEN}[+] Processing: {profile_info.get('name', 'Unknown')} at {profile_info.get('company', 'Unknown')}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}[+] Company domain: {profile_info.get('company_domain', 'Unknown')}{Style.RESET_ALL}")
        
        # Default domains to check (only used if no company domain found)
        domains = []
        
        # Add additional domains if provided
        if additional_domains:
            domains.extend(additional_domains)
        
        # Generate possible email patterns
        possible_emails = self.generate_email_patterns(profile_info, domains)
        
        # Verify emails
        verified_emails = []
        print(f"{Fore.BLUE}[*] Checking {len(possible_emails)} possible email addresses...{Style.RESET_ALL}")
        
        for email in tqdm(possible_emails, desc="Verifying emails"):
            is_valid, confidence = self.verify_email(email)
            if is_valid:
                verified_emails.append({
                    'email': email,
                    'confidence': confidence,
                    'source': 'pattern_matching'
                })
            
            # Add a small delay to avoid rate limiting
            self._random_delay()
        
        # Sort by confidence
        verified_emails.sort(key=lambda x: 0 if x['confidence'] == 'High' else (1 if x['confidence'] == 'Medium' else 2))
        
        return verified_emails
    
    def cleanup(self):
        """Clean up resources"""
        self._close_driver()

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Find emails based on name and company')
    parser.add_argument('--first-name', required=True, help='First name of the person')
    parser.add_argument('--last-name', required=True, help='Last name of the person')
    parser.add_argument('--company', required=True, help='Company name')
    parser.add_argument('--domains', nargs='+', help='Additional domains to check')
    parser.add_argument('--no-headless', action='store_true', help='Run browser in visible mode')
    parser.add_argument('--config', help='Path to configuration file (JSON)')
    parser.add_argument('--api-key', help='Google Custom Search API key (overrides env variable)')
    parser.add_argument('--search-engine-id', help='Google Custom Search Engine ID (overrides env variable)')
    args = parser.parse_args()
    
    # If API key is provided as command line argument, use it
    api_key = args.api_key or os.getenv("GOOGLE_API_KEY", "AIzaSyCrHZyNJKLY62UW7ZUY6X4acgSVxCWFAes")
    search_engine_id = args.search_engine_id or os.getenv("GOOGLE_SEARCH_ENGINE_ID", "")
    
    finder = EmailFinder(
        headless=not args.no_headless, 
        config_path=args.config,
        api_key=api_key,
        search_engine_id=search_engine_id
    )
    
    try:
        emails = finder.find_emails(args.first_name, args.last_name, args.company, args.domains)
        
        if emails:
            print(f"\n{Fore.GREEN}[+] Found {len(emails)} potential email addresses:{Style.RESET_ALL}")
            for i, email_info in enumerate(emails, 1):
                confidence_color = Fore.GREEN if email_info['confidence'] == 'High' else (Fore.YELLOW if email_info['confidence'] == 'Medium' else Fore.RED)
                print(f"{i}. {email_info['email']} - Confidence: {confidence_color}{email_info['confidence']}{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.YELLOW}[!] No email addresses found{Style.RESET_ALL}")
    
    finally:
        finder.cleanup()

if __name__ == '__main__':
    main()
