import imaplib
import email
from email.header import decode_header
import sqlite3
import logging
import backoff
from analyze_email import analyze_email
import json

class EmailWatcher:
    """A class for watching and processing job-related emails."""

    def __init__(self, email_address, password, inbox, imap_server):
        """Initialize the EmailWatcher with email settings."""
        self.connect_attempts = 0
        self.max_connect_attempts = 3
        self.email_address = email_address
        self.password = password
        self.inbox = inbox
        self.imap_server = imap_server
        self.mail = None
        self.stop_flag = False

    @backoff.on_exception(backoff.expo, imaplib.IMAP4.error, max_tries=3)
    def connect(self):
        """Connect to the IMAP server with exponential backoff."""
        try:
            self.mail = imaplib.IMAP4_SSL(self.imap_server)
            self.mail.login(self.email_address, self.password)
            self.mail.select(self.inbox)
            logging.debug(f"Successfully connected to {self.imap_server}")
            return True
        except imaplib.IMAP4.error as e:
            logging.error(f"Error connecting to {self.imap_server}: {e}")
            return False

    def fetch_new_emails(self, last_checked):
        """Fetch new emails from the inbox since the last checked time."""
        try:
            self.mail.select(self.inbox)
            date_string = last_checked.strftime("%d-%b-%Y")
            _, search_data = self.mail.search(None, f'(SINCE "{date_string}")')
            for num in search_data[0].split():
                try:
                    _, data = self.mail.fetch(num, '(RFC822)')
                    raw_email = data[0][1]
                    email_message = email.message_from_bytes(raw_email)
                    yield num, email_message
                except Exception as e:
                    logging.error(f"Error fetching email {num}: {e}")
        except imaplib.IMAP4.error as e:
            logging.error(f"IMAP4 error during fetch: {e}")
        except Exception as e:
            logging.error(f"Unexpected error during fetch: {e}")

    def parse_email(self, email_message):
        """Parse an email message and extract relevant information."""
        try:
            subject = self.decode_header(email_message.get("Subject", ""))
            sender = email.utils.parseaddr(email_message.get("From", ""))[1]
            date = email.utils.parsedate_to_datetime(email_message.get("Date"))

            body = ""
            if email_message.is_multipart():
                for part in email_message.walk():
                    if part.get_content_type() == "text/plain":
                        body = self.decode_payload(part)
                        break
            else:
                body = self.decode_payload(email_message)

            return {"subject": subject, "sender": sender, "date": date, "body": body}
        except Exception as e:
            logging.error(f"Error parsing email: {e}")
            return None

    def decode_header(self, header):
        """Decode email header."""
        try:
            decoded_header, encoding = decode_header(header)[0]
            if isinstance(decoded_header, bytes):
                return decoded_header.decode(encoding or "utf-8", errors="replace")
            return decoded_header
        except Exception as e:
            logging.error(f"Error decoding header: {e}")
            return ""

    def decode_payload(self, part):
        """Decode email payload."""
        try:
            payload = part.get_payload(decode=True)
            charset = part.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
        except Exception as e:
            logging.error(f"Error decoding payload: {e}")
            return ""

    def interpret_email(self, email_data):
        """Interpret the email content using the ChatGPT parser."""
        email_content = f"Subject: {email_data['subject']}\n\n{email_data['body']}"
        parsed_result = analyze_email(email_content)
        
        try:
            result = json.loads(parsed_result)
            if result['job_related']:
                return {
                    "company": result['company_name'],
                    "position": result['job_position'],
                    "status": result['application_status'],
                    "date": email_data["date"].strftime("%Y-%m-%d"),
                    "notes": result['email_content'],
                }
            else:
                return None
        except json.JSONDecodeError:
            logging.error(f"Error decoding JSON from ChatGPT: {parsed_result}")
            return None

    @backoff.on_exception(backoff.expo, sqlite3.Error, max_tries=3)
    def update_database(self, job_data):
        """Update the job application database with extracted information."""
        try:
            conn = sqlite3.connect("job_applications.db", timeout=10)
            cursor = conn.cursor()

            # Check if the job already exists based on company and position
            cursor.execute("""
                SELECT id, status 
                FROM jobs 
                WHERE company = ? AND position = ?
            """, (job_data["company"], job_data["position"]))
            existing_job = cursor.fetchone()

            if existing_job:
                job_id, current_status = existing_job
                if job_data["status"] != current_status:
                    cursor.execute("""
                        UPDATE jobs 
                        SET status = ?, last_updated = ?, notes = notes || '\n\n' || ?, updated = 1
                        WHERE id = ?
                    """, (job_data["status"], job_data["date"], job_data["notes"], job_id))
                else:
                    cursor.execute("""
                        UPDATE jobs 
                        SET last_updated = ?, notes = notes || '\n\n' || ?
                        WHERE id = ?
                    """, (job_data["date"], job_data["notes"], job_id))
                
                logging.debug(f"Updated existing job: {job_data['company']} - {job_data['position']}")
            else:
                # Insert new job
                cursor.execute("""
                    INSERT INTO jobs (company, position, status, application_date, last_updated, notes, updated) 
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                """, (job_data["company"], job_data["position"], job_data["status"], job_data["date"], 
                      job_data["date"], job_data["notes"]))
                job_id = cursor.lastrowid
                logging.debug(f"Inserted new job: {job_data['company']} - {job_data['position']}")

            conn.commit()
            logging.debug(f"Database updated for job: {job_data['company']} - {job_data['position']}")
        except sqlite3.Error as e:
            logging.error(f"Database error: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

    def process_email(self, email_id, email_message):
        """Process a single email message."""
        email_data = self.parse_email(email_message)
        if email_data:
            job_data = self.interpret_email(email_data)
            if job_data:
                self.update_database(job_data)
            else:
                logging.debug(f"Email {email_id} not interpreted as job-related")
        else:
            logging.warning(f"Failed to parse email {email_id}")

    def run(self, last_checked):
        """Main method to run the email watcher."""
        try:
            if self.connect():
                logging.debug(f"Starting to fetch new emails since {last_checked}")
                for email_id, email_message in self.fetch_new_emails(last_checked):
                    if self.stop_flag:
                        break
                    logging.debug(f"Processing email {email_id}")
                    self.process_email(email_id, email_message)
                logging.debug("Finished processing emails")
        except imaplib.IMAP4.error as e:
            logging.error(f"IMAP4 error: {e}")
        except ConnectionError as e:
            logging.error(f"Connection error: {e}")
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
        finally:
            if self.mail:
                try:
                    self.mail.logout()
                    logging.debug("Successfully logged out from email server")
                except Exception as e:
                    logging.error(f"Error during logout: {e}")