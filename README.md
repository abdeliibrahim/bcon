# Business Contact & Outreach Network (BCON)

A tool to find and manage business contacts using first name, last name, and company information, similar to RocketReach but free and self-hosted.

## Features

- Find email addresses using first name, last name, and company information
- Automatically determine company domains
- Discover email formats used by companies through Google search
- Generate potential email addresses based on discovered formats or common patterns
- Verify email addresses using direct SMTP verification without sending emails
- Support for custom domains
- Both command-line and web interfaces

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd bcon
```

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

3. Make sure you have Chrome installed (required for Selenium).

4. Run the setup script:
```bash
chmod +x setup.sh
./setup.sh
```

## Usage

### Command-Line Interface

#### Basic Usage

```bash
python email_finder.py --first-name John --last-name Doe --company XCompany
```

#### With Additional Domains

```bash
python email_finder.py --first-name John --last-name Doe --company XCompany --domains gmail.com otherdomain.com
```

#### Run with Visible Browser (In Development)

```bash
python email_finder.py --first-name John --last-name Doe --company XCompany --no-headless
```

### Web Interface

1. Start the web server:
```bash
python app.py
```

2. Open your browser and navigate to `http://localhost:5000`

3. Enter the person's first name, last name, and company name, then click "Find Emails"

## How It Works

1. **Company Domain Discovery**: The tool attempts to determine the company's domain by first trying a direct approach (companyname.com) and then using Google search if needed.

2. **Email Format Search**: The tool searches Google for "email format for X company" to find the common email pattern used by the company (e.g., firstname.lastname@company.com).

3. **Email Pattern Generation**: Based on the discovered format or using common patterns, the tool generates potential email addresses.

4. **Email Verification**: The tool attempts to verify each potential email using multiple methods:
   - Email format validation
   - Domain MX record check
   - Direct SMTP verification (checking if the mailbox exists without sending an email)

5. **Results Presentation**: Verified emails are presented with a confidence score.

## Limitations

- Email verification accuracy depends on the mail server's configuration. Some servers may not reject invalid recipients during the SMTP handshake.
- Google searches may be rate-limited if used extensively.
- The tool may not work if verification services change their page structure.

## Disclaimer

This tool is for educational purposes only. Use responsibly and respect privacy laws. The author is not responsible for any misuse of this tool.

## License

MIT
