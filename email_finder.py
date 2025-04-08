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
from urllib.parse import urlparse, quote_plus
from typing import List, Dict, Any, Optional, Tuple

import requests
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
        }
    }
    
    def __init__(self, headless: bool = True, config_path: str = None):
        """Initialize the Email Finder
        
        Args:
            headless: Whether to run the browser in headless mode
            config_path: Path to configuration file (JSON)
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
        
        # Initialize Selenium WebDriver settings
        self.headless = headless
        self.driver = None
        
        # We'll still keep a requests session for simple operations
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': random.choice(self.config['user_agents']),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.google.com/'
        })
        
    def _initialize_driver(self):
        """Initialize the Selenium WebDriver"""
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
    
    def _handle_captcha(self, driver):
        """Handle CAPTCHA or redirect pages
        
        Args:
            driver: Selenium WebDriver instance
            
        Returns:
            bool: True if CAPTCHA was handled successfully
        """
        try:
            # Check for common CAPTCHA indicators in the page source
            page_source = driver.page_source.lower()
            captcha_indicators = [
                "please click here if you are not redirected",
                "click here to continue",
                "i am not a robot",
                "please complete the security check",
                "unusual traffic from your computer network",
                "we need to make sure that you are not a robot",
                "captcha",
                "recaptcha"
            ]
            
            captcha_detected = any(indicator in page_source for indicator in captcha_indicators)
            
            if not captcha_detected:
                return False  # No CAPTCHA detected
            
            print(f"{Fore.YELLOW}[!] CAPTCHA detected, attempting to solve...{Style.RESET_ALL}")
            
            # Look for common CAPTCHA or redirect elements
            redirect_selectors = [
                "//a[contains(text(), 'please click here if you are not redirected')]",
                "//a[contains(text(), 'click here to continue')]",
                "//a[contains(text(), 'I am not a robot')]",
                "//button[contains(text(), 'Continue')]",
                "//input[@type='submit' and @value='Continue']",
                "//div[@id='recaptcha']",
                "//iframe[contains(@src, 'recaptcha')]"
            ]
            
            for selector in redirect_selectors:
                try:
                    elements = driver.find_elements(By.XPATH, selector)
                    if elements:
                        print(f"{Fore.YELLOW}[!] Found CAPTCHA/redirect element, clicking...{Style.RESET_ALL}")
                        elements[0].click()
                        
                        # Wait for page to load after clicking
                        WebDriverWait(driver, 10).until(
                            lambda d: d.execute_script('return document.readyState') == 'complete'
                        )
                        
                        # Add a longer delay after handling CAPTCHA
                        self._random_delay("after_captcha")
                        return True
                except (TimeoutException, NoSuchElementException, WebDriverException) as e:
                    print(f"{Fore.YELLOW}[!] Error clicking element: {str(e)}{Style.RESET_ALL}")
                    continue
            
            # Check for reCAPTCHA iframe and try to handle it
            try:
                iframes = driver.find_elements(By.XPATH, "//iframe[contains(@src, 'recaptcha')]")
                if iframes:
                    print(f"{Fore.YELLOW}[!] Found reCAPTCHA iframe, switching to it...{Style.RESET_ALL}")
                    driver.switch_to.frame(iframes[0])
                    
                    # Try to find and click the checkbox
                    checkboxes = driver.find_elements(By.XPATH, "//div[@class='recaptcha-checkbox-border']")
                    if checkboxes:
                        checkboxes[0].click()
                        print(f"{Fore.GREEN}[+] Clicked reCAPTCHA checkbox{Style.RESET_ALL}")
                        
                        # Switch back to main content
                        driver.switch_to.default_content()
                        
                        # Wait for the verification to complete
                        self._random_delay("after_captcha")
                        
                        # Try to find and click the submit button after solving CAPTCHA
                        submit_buttons = driver.find_elements(By.XPATH, "//input[@type='submit'] | //button[contains(text(), 'Submit')]")
                        if submit_buttons:
                            submit_buttons[0].click()
                            print(f"{Fore.GREEN}[+] Clicked submit button after CAPTCHA{Style.RESET_ALL}")
                        
                        return True
            except Exception as e:
                print(f"{Fore.YELLOW}[!] Error handling reCAPTCHA: {str(e)}{Style.RESET_ALL}")
                driver.switch_to.default_content()  # Make sure we're back to the main frame
            
            # If we get here, we couldn't automatically solve the CAPTCHA
            if not self.headless:
                print(f"{Fore.YELLOW}[!] Waiting for manual CAPTCHA solving...{Style.RESET_ALL}")
                # If in visible mode, give the user time to solve the CAPTCHA manually
                time.sleep(20)  # Wait for manual intervention
                return True
            
            return False
        except Exception as e:
            print(f"{Fore.YELLOW}[!] Error in CAPTCHA handling: {str(e)}{Style.RESET_ALL}")
            return False
    
    def _safe_selenium_get(self, url, max_attempts=None, retry_delay_factor=None):
        """Safely navigate to a URL with Selenium, handling CAPTCHAs and retries
        
        Args:
            url: URL to navigate to
            max_attempts: Maximum number of retry attempts (default from config)
            retry_delay_factor: Backoff factor for retries (default from config)
            
        Returns:
            bool: True if navigation was successful
        """
        if max_attempts is None:
            max_attempts = self.config["retries"]["max_attempts"]
        
        if retry_delay_factor is None:
            retry_delay_factor = self.config["retries"]["backoff_factor"]
        
        self._initialize_driver()
        
        for attempt in range(max_attempts):
            try:
                print(f"{Fore.BLUE}[*] Navigating to {url}...{Style.RESET_ALL}")
                self.driver.get(url)
                
                # Wait for page to load
                try:
                    WebDriverWait(self.driver, 15).until(
                        lambda d: d.execute_script('return document.readyState') == 'complete'
                    )
                except TimeoutException:
                    print(f"{Fore.YELLOW}[!] Page load timeout, but continuing...{Style.RESET_ALL}")
                
                # Check for CAPTCHA and handle it
                if "captcha" in self.driver.page_source.lower() or "please click here" in self.driver.page_source.lower():
                    if not self._handle_captcha(self.driver):
                        # If CAPTCHA handling failed, wait and retry
                        delay = retry_delay_factor ** attempt
                        print(f"{Fore.YELLOW}[!] CAPTCHA handling failed, retrying in {delay:.1f} seconds (attempt {attempt+1}/{max_attempts})...{Style.RESET_ALL}")
                        time.sleep(delay)
                        continue
                
                # Add a small delay to ensure the page is fully loaded
                time.sleep(2)
                
                # If we get here, navigation was successful
                return True
                
            except Exception as e:
                delay = retry_delay_factor ** attempt
                print(f"{Fore.YELLOW}[!] Error navigating to {url}: {str(e)}, retrying in {delay:.1f} seconds (attempt {attempt+1}/{max_attempts})...{Style.RESET_ALL}")
                time.sleep(delay)
        
        print(f"{Fore.RED}[!] Failed to navigate to {url} after {max_attempts} attempts{Style.RESET_ALL}")
        return False

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
        """Get the domain for a company using Selenium
        
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
            
            # If direct approach fails, try Google search with Selenium
            search_query = f"{clean_company} company website"
            search_url = f"https://www.google.com/search?q={quote_plus(search_query)}"
            
            if self._safe_selenium_get(search_url):
                # Wait for search results
                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.ID, "search"))
                    )
                    
                    # Parse results
                    soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                    results = soup.select('.tF2Cxc')
                    
                    for result in results[:3]:  # Check top 3 results
                        link = result.select_one('.yuRUbf a')
                        if link and 'href' in link.attrs:
                            url = link['href']
                            parsed_url = urlparse(url)
                            if parsed_url.netloc and '.' in parsed_url.netloc:
                                domain = parsed_url.netloc
                                if domain.startswith('www.'):
                                    domain = domain[4:]
                                return domain
                except Exception as e:
                    print(f"{Fore.YELLOW}[!] Error parsing search results: {str(e)}{Style.RESET_ALL}")
            
            # Try a second search with a different query
            search_query2 = f"{company_name} company email format"
            search_url2 = f"https://www.google.com/search?q={quote_plus(search_query2)}"
            
            if self._safe_selenium_get(search_url2):
                # Wait for search results
                try:
                    # Wait for the search results to load
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.g"))
                    )
                    
                    # Get the page source after everything is loaded
                    page_source = self.driver.page_source
                    
                    # Parse the HTML
                    soup = BeautifulSoup(page_source, 'html.parser')
                    
                    # Get all search result snippets
                    snippets = []
                    
                    # Try different CSS selectors that Google might use
                    for selector in ['div.VwiC3b', 'div.aCOpRe', 'span.aCOpRe', 'div.s3v9rd', 'div.Z26q7c']:
                        elements = soup.select(selector)
                        for element in elements:
                            if element.text and len(element.text.strip()) > 20:  # Ignore very short snippets
                                snippets.append(element.text.lower())
                    
                    # Look for patterns in snippets
                    for snippet in snippets:
                        for format_name, patterns in self.config["email_formats"].items():
                            for pattern in patterns:
                                if pattern in snippet:
                                    print(f"{Fore.GREEN}[+] Found email format from second search: {format_name}{Style.RESET_ALL}")
                                    return format_name
                except Exception as e:
                    print(f"{Fore.YELLOW}[!] Error parsing second search results: {str(e)}{Style.RESET_ALL}")
            
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
            print(f"{Fore.RED}[!] Error finding company domain: {str(e)}{Style.RESET_ALL}")
            # Return the default format from config
            return self.config["default_email_format"]
            
    def find_email_format(self, company_domain: str) -> Optional[str]:
        """Find the email format used by a company through Google search using Selenium
        
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
            search_query = f"{company_name} email format leadiq"
            search_url = f"https://www.google.com/search?q={quote_plus(search_query)}"
            
            if self._safe_selenium_get(search_url):
                # Wait for search results
                try:
                    # Wait for the search results to load
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.g"))
                    )
                    
                    # Get the page source after everything is loaded
                    page_source = self.driver.page_source
                    
                    # Parse the HTML
                    soup = BeautifulSoup(page_source, 'html.parser')
                    
                    # Get all search result snippets
                    snippets = []
                    
                    # Try different CSS selectors that Google might use
                    for selector in ['div.VwiC3b', 'div.aCOpRe', 'span.aCOpRe', 'div.s3v9rd', 'div.Z26q7c']:
                        elements = soup.select(selector)
                        for element in elements:
                            if element.text and len(element.text.strip()) > 20:  # Ignore very short snippets
                                snippets.append(element.text.lower())
                    
                    # Look for patterns in snippets
                    for snippet in snippets:
                        for format_name, patterns in common_formats.items():
                            for pattern in patterns:
                                if pattern in snippet:
                                    print(f"{Fore.GREEN}[+] Found email format: {format_name}{Style.RESET_ALL}")
                                    return format_name
                except Exception as e:
                    print(f"{Fore.YELLOW}[!] Error parsing search results: {str(e)}{Style.RESET_ALL}")
            
            # Try a second search with a different query
            search_query2 = f"{company_name} company email format"
            search_url2 = f"https://www.google.com/search?q={quote_plus(search_query2)}"
            
            if self._safe_selenium_get(search_url2):
                # Wait for search results
                try:
                    # Wait for the search results to load
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.g"))
                    )
                    
                    # Get the page source after everything is loaded
                    page_source = self.driver.page_source
                    
                    # Parse the HTML
                    soup = BeautifulSoup(page_source, 'html.parser')
                    
                    # Get all search result snippets
                    snippets = []
                    
                    # Try different CSS selectors that Google might use
                    for selector in ['div.VwiC3b', 'div.aCOpRe', 'span.aCOpRe', 'div.s3v9rd', 'div.Z26q7c']:
                        elements = soup.select(selector)
                        for element in elements:
                            if element.text and len(element.text.strip()) > 20:  # Ignore very short snippets
                                snippets.append(element.text.lower())
                    
                    # Look for patterns in snippets
                    for snippet in snippets:
                        for format_name, patterns in common_formats.items():
                            for pattern in patterns:
                                if pattern in snippet:
                                    print(f"{Fore.GREEN}[+] Found email format from second search: {format_name}{Style.RESET_ALL}")
                                    return format_name
                except Exception as e:
                    print(f"{Fore.YELLOW}[!] Error parsing second search results: {str(e)}{Style.RESET_ALL}")
            
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
    args = parser.parse_args()
    
    finder = EmailFinder(headless=not args.no_headless, config_path=args.config)
    
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
