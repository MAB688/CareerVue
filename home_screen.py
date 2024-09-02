import logging
import time
import customtkinter as ctk
import sqlite3
from CTkMessagebox import CTkMessagebox
from datetime import datetime
import threading
import json
import os
from email_watcher import EmailWatcher
from notes_window import NotesWindow
from email_config_dialog import EmailConfigDialog

class HomeScreen(ctk.CTk):
    """The main application window for the job tracker."""

    def __init__(self):
        super().__init__()
        
        # Delete old log file
        if os.path.exists("email_watcher.log"):
            try:
                os.remove("email_watcher.log")
                print(f"Log file 'email_watcher.log' deleted successfully.")
            except Exception as e:
                print(f"Error deleting log file 'email_watcher.log': {e}")
        else:
            print(f"Log file 'email_watcher.log' does not exist.")
    
        self.title("CareerVue - Job Application Tracker")
        self.geometry("1200x600")

        # Configure main grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Initialize variables
        self.job_rows = {}  # Store references to job rows
        self.next_row = 1  # Start job rows from row 1 (after headers)
        self.email_watcher = None
        self.email_watcher_thread = None

        # Set up UI components
        self.setup_top_frame()
        self.setup_main_frame()
        self.setup_jobs_frame()
        
        self.config = self.load_config()

        if self.config == {}:
            self.open_email_config()

        self.start_email_watcher()

        # Refresh job list
        self.refresh_jobs()

    def setup_top_frame(self):
        """Set up the top frame with logo, add button, and refresh button."""
        self.top_frame = ctk.CTkFrame(self)
        self.top_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=10)
        self.top_frame.grid_columnconfigure(1, weight=1)

        self.logo_label = ctk.CTkLabel(self.top_frame, text="CareerVue", font=ctk.CTkFont(size=24, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")

        self.email_config_button = ctk.CTkButton(self.top_frame, text="Add Email Config", command=self.open_email_config)
        self.email_config_button.grid(row=0, column=1, padx=10, pady=10)

        self.refresh_button = ctk.CTkButton(self.top_frame, text="Refresh", width=40, font=("Arial", 14), command=self.refresh_emails_and_jobs)
        self.refresh_button.grid(row=0, column=2, padx=10, pady=10, sticky="e")

        self.add_job_button = ctk.CTkButton(self.top_frame, text="+", width=40, font=("Arial", 20), command=self.add_new_job)
        self.add_job_button.grid(row=0, column=3, padx=10, pady=10, sticky="e")

        # Add last sync time label
        self.last_sync_label = ctk.CTkLabel(self.top_frame, text="Last sync: Never", font=("Arial", 12))
        self.last_sync_label.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="w")

        # Add email watcher status indicator
        self.status_indicator = ctk.CTkLabel(self.top_frame, text="●", font=("Arial", 20), text_color="red")
        self.status_indicator.grid(row=1, column=2, padx=10, pady=(0, 10), sticky="e")

        self.update_sync_time()
        self.update_status_indicator()

    def update_sync_time(self):
        """Update the last sync time label."""
        try:
            with open('last_checked.json', 'r') as f:
                data = json.load(f)
                last_checked = datetime.fromisoformat(data['last_checked'])
                self.last_sync_label.configure(text=f"Last sync: {last_checked.strftime('%Y-%m-%d %H:%M:%S')}")
        except FileNotFoundError:
            self.last_sync_label.configure(text="Last sync: Never")
        except json.JSONDecodeError:
            self.last_sync_label.configure(text="Last sync: Error reading file")

    def update_status_indicator(self):
        """Update the email watcher status indicator."""
        if self.email_watcher and self.email_watcher.connect():
            self.status_indicator.configure(text_color="green")
        else:
            self.status_indicator.configure(text_color="red")

    def setup_main_frame(self):
        """Set up the main frame that will contain the jobs list."""
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)

    def setup_jobs_frame(self):
        """Set up the scrollable frame for job entries and headers."""
        self.jobs_frame = ctk.CTkScrollableFrame(self.main_frame)
        self.jobs_frame.grid(row=0, column=0, sticky="nsew")
        self.jobs_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)
        self.jobs_frame.grid_columnconfigure((5, 6), weight=0)  # Notes and Delete columns

        # Add headers with larger font
        headers = ["Company", "Position", "Status", "Application Date", "Last Updated", "", ""]
        for i, header in enumerate(headers):
            label = ctk.CTkLabel(self.jobs_frame, text=header, font=ctk.CTkFont(size=16, weight="bold"))
            label.grid(row=0, column=i, padx=5, pady=(5, 10), sticky="ew")
            if i < 5:  # Center text for all columns except Notes and Delete
                label.configure(anchor="center")

    def refresh_emails_and_jobs(self):
        """Refresh emails and update the job list."""
        if self.email_watcher:
            try:
                self.email_watcher.run()
                self.refresh_jobs()
                self.update_sync_time()
                self.update_status_indicator()
                CTkMessagebox(title="Success", message="Emails checked and jobs refreshed!", icon="info")
            except Exception as e:
                print(f"Error refreshing emails: {e}")
                CTkMessagebox(title="Error", message="Failed to refresh emails. Please try again.", icon="cancel")
        else:
            CTkMessagebox(title="Error", message="Email watcher not configured. Please set up email configuration first.", icon="cancel")

    def load_config(self):
        try:
            with open("email_config.json", "r") as f:
                config = json.load(f)
        except FileNotFoundError:
            print("Error: The file 'email_config.json' was not found.")
            config = {}  # Assign a default empty dictionary or other default values
        except json.JSONDecodeError:
            print("Error: Failed to decode JSON. The file may be corrupted or improperly formatted.")
            config = {}  # Assign a default empty dictionary or other default values
        except IOError as e:
            print(f"Error: An I/O error occurred: {e}")
            config = {}  # Assign a default empty dictionary or other default values
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            config = {}  # Assign a default empty dictionary or other default values

        return config

    def update_config(self, new_config):
        """Update the email configuration and restart the email watcher."""
        self.config = new_config
        if self.email_watcher:
            self.stop_email_watcher()
        self.start_email_watcher()
        self.update_status_indicator()
        self.update_sync_time()

    def start_email_watcher(self):
        """Start the email watcher thread."""
        if not self.config:
            return

        required_keys = ["email", "password", "inbox", "imap_server"]
        if not all(key in self.config for key in required_keys):
            CTkMessagebox(title="Error", message="Email configuration incomplete. Please check your credentials and try again", icon="cancel")
            return
        
        self.email_watcher = EmailWatcher(self.config["email"], 
                                          self.config["password"], 
                                          self.config["inbox"], 
                                          self.config["imap_server"])
        
        # Test connection before starting the thread
        if self.email_watcher.connect():
            self.email_watcher_thread = threading.Thread(target=self.run_email_watcher, daemon=True)
            self.email_watcher_thread.start()
            self.update_status_indicator()
            print("Email watcher started successfully!")
        else:
            self.update_status_indicator()
            CTkMessagebox(title="Error", message="Failed to connect to email server. Please check your credentials and try again.", icon="cancel")

    def run_email_watcher(self):
        """Run the email watcher continuously."""
        while not getattr(self.email_watcher, 'stop_flag', False):
            try:
                print("Running email watcher")
                self.email_watcher.run()
                self.update_sync_time()
                # Sleep for 5 minutes before checking again
                # This should be configurable
                time.sleep(300)
            except Exception as e:
                print(f"Error in email watcher: {e}")
                # Sleep for 1 minute before retrying
                time.sleep(60)
            finally:
                self.update_status_indicator()
    
    def stop_email_watcher(self):
        """Stop the current email watcher thread."""
        if self.email_watcher and self.email_watcher_thread and self.email_watcher_thread.is_alive():
            self.email_watcher.stop_flag = True
            self.email_watcher_thread.join(timeout=5)  # Wait for the thread to finish
        self.email_watcher = None
        self.email_watcher_thread = None

    def add_new_job(self):
        """Add a new job entry to the database and UI."""
        conn = sqlite3.connect("job_applications.db")
        cursor = conn.cursor()
        current_date = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("""
            INSERT INTO jobs (company, position, status, application_date, last_updated, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("New Company", "New Position", "Applied", current_date, current_date, ""))
        job_id = cursor.lastrowid
        conn.commit()
        conn.close()
        self.add_job_row(job_id, "New Company", "New Position", "Applied", current_date, current_date, "")

    def delete_job(self, job_id):
        """Delete a job entry from the database and UI."""
        confirm = CTkMessagebox(title="Confirm Deletion", message="Are you sure you want to delete this job?", icon="question", option_1="Yes", option_2="No")
        if confirm.get() == "Yes":
            conn = sqlite3.connect("job_applications.db")
            cursor = conn.cursor()
            
            # Get the email hash before deleting the job
            cursor.execute("SELECT email_hash FROM jobs WHERE id=?", (job_id,))
            result = cursor.fetchone()
            
            if result:
                email_hash = result[0]
                
                # Delete the job from the database
                cursor.execute("DELETE FROM jobs WHERE id=?", (job_id,))
                conn.commit()
                
                # Remove the job row from the UI
                self.remove_job_row(job_id)
                
                # Remove the email hash from the EmailWatcher's cache
                if self.email_watcher:
                    self.email_watcher.remove_processed_hash(email_hash)
                
                logging.info(f"Deleted job with ID {job_id} and removed hash {email_hash} from cache")
            else:
                logging.warning(f"Attempted to delete non-existent job with ID {job_id}")
            
            conn.close()

    def validate_and_update(self, job_id, field, value, widget):
        """Validate user input and update the job if valid."""
        error = None
        if field in ["company", "position"] and not value.strip():
            error = f"{field.capitalize()} cannot be empty."
        elif field == "application_date":
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                error = "Invalid date. Please use YYYY-MM-DD format."

        if error:
            CTkMessagebox(title="Validation Error", message=error, icon="cancel")
            widget.delete(0, ctk.END)
            widget.insert(0, self.get_original_value(job_id, field))
        else:
            self.update_job(job_id, field, value)

    def get_original_value(self, job_id, field):
        """Retrieve the original value of a field from the database."""
        conn = sqlite3.connect("job_applications.db")
        cursor = conn.cursor()
        cursor.execute(f"SELECT {field} FROM jobs WHERE id = ?", (job_id,))
        value = cursor.fetchone()[0]
        conn.close()
        return value

    def update_job(self, job_id, field, value): 
        """Update a job field in the database and UI."""
        conn = sqlite3.connect("job_applications.db")
        cursor = conn.cursor()
        try:
            current_date = datetime.now().strftime("%Y-%m-%d")
            cursor.execute(f"UPDATE jobs SET {field} = ?, last_updated = ? WHERE id = ?", 
                           (value, current_date, job_id))
            conn.commit()
            self.update_job_row(job_id, field, value)
            if field != "notes":
                self.update_job_row(job_id, "last_updated", current_date)
        except sqlite3.Error as e:
            print(f"An error occurred: {e}")
            CTkMessagebox(title="Database Error", message="An error occurred while updating the job.", icon="cancel")
        finally:
            conn.close()

    def open_notes(self, job_id, notes):
        """Open the notes window for a specific job."""
        NotesWindow(self, job_id, notes)

    def refresh_jobs(self):
        """Refresh the job list from the database."""
        conn = sqlite3.connect("job_applications.db")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs ORDER BY last_updated DESC")
        jobs = cursor.fetchall()
        conn.close()

        # Keep track of job IDs to remove
        existing_job_ids = set(self.job_rows.keys())

        for job in jobs:
            job_id, company, position, status, app_date, last_updated, notes, email_hash = job
            if job_id not in self.job_rows:
                self.add_job_row(job_id, company, position, status, app_date, last_updated, notes)
            else:
                self.update_job_row(job_id, "company", company)
                self.update_job_row(job_id, "position", position)
                self.update_job_row(job_id, "status", status)
                self.update_job_row(job_id, "application_date", app_date)
                self.update_job_row(job_id, "last_updated", last_updated)
            existing_job_ids.discard(job_id)

        # Remove any jobs that are no longer in the database
        for job_id in existing_job_ids:
            self.remove_job_row(job_id)

    def add_job_row(self, job_id, company, position, status, app_date, last_updated, notes):
        """Add a new job row to the UI."""
        row = self.next_row
        self.next_row += 1

        # Create and place widgets for each job field
        company_entry = ctk.CTkEntry(self.jobs_frame, width=150)
        company_entry.insert(0, company)
        company_entry.grid(row=row, column=0, padx=5, pady=(10, 2), sticky="ew")
        company_entry.bind("<FocusOut>", lambda e, j=job_id, w=company_entry: self.validate_and_update(j, "company", w.get(), w))

        position_entry = ctk.CTkEntry(self.jobs_frame, width=150)
        position_entry.insert(0, position)
        position_entry.grid(row=row, column=1, padx=5, pady=(10, 2), sticky="ew")
        position_entry.bind("<FocusOut>", lambda e, j=job_id, w=position_entry: self.validate_and_update(j, "position", w.get(), w))

        status_var = ctk.StringVar(value=status)
        status_dropdown = ctk.CTkOptionMenu(self.jobs_frame, variable=status_var, values=["Applied", "Interview", "Offer", "Rejected"], width=100)
        status_dropdown.grid(row=row, column=2, padx=5, pady=(10, 2), sticky="ew")
        status_dropdown.configure(command=lambda v, j=job_id: self.update_job(j, "status", v))

        app_date_entry = ctk.CTkEntry(self.jobs_frame, width=100)
        app_date_entry.insert(0, app_date)
        app_date_entry.grid(row=row, column=3, padx=5, pady=(10, 2), sticky="ew")
        app_date_entry.bind("<FocusOut>", lambda e, j=job_id, w=app_date_entry: self.validate_and_update(j, "application_date", w.get(), w))

        last_updated_label = ctk.CTkLabel(self.jobs_frame, text=last_updated, width=100)
        last_updated_label.grid(row=row, column=4, padx=5, pady=(10, 2), sticky="ew")

        notes_button = ctk.CTkButton(self.jobs_frame, text="Notes", width=50, 
                                     command=lambda j=job_id, n=notes: self.open_notes(j, n))
        notes_button.grid(row=row, column=5, padx=5, pady=(10, 2))

        delete_button = ctk.CTkButton(self.jobs_frame, text="✕", width=30, height=30, 
                                      fg_color="red", hover_color="dark red",
                                      command=lambda j=job_id: self.delete_job(j))
        delete_button.grid(row=row, column=6, padx=(5, 10), pady=(10, 2))

        # Store references to row widgets
        self.job_rows[job_id] = {
            "row": row,
            "company": company_entry,
            "position": position_entry,
            "status": status_dropdown,
            "application_date": app_date_entry,
            "last_updated": last_updated_label,
            "notes": notes_button,
            "delete": delete_button
        }

    def update_job_row(self, job_id, field, value):
        """Update a specific field in a job row."""
        if job_id in self.job_rows:
            if field == "last_updated":
                self.job_rows[job_id]["last_updated"].configure(text=value)
            elif field in ["company", "position", "application_date"]:
                if field in self.job_rows[job_id]:
                    self.job_rows[job_id][field].delete(0, ctk.END)
                    self.job_rows[job_id][field].insert(0, value)
                else:
                    print(f"Warning: Field '{field}' not found in job_rows for job_id {job_id}")
            elif field == "status":
                self.job_rows[job_id]["status"].set(value)
            elif field == "notes":
                # We don't need to update the UI for notes, as it's handled in a separate window
                pass
            else:
                print(f"Warning: Unhandled field '{field}' in update_job_row")

    def remove_job_row(self, job_id):
        """Remove a job row from the UI and adjust remaining rows."""
        if job_id in self.job_rows:
            row = self.job_rows[job_id]["row"]
            
            # Destroy all widgets in the row
            for widget in self.job_rows[job_id].values():
                if isinstance(widget, (ctk.CTkEntry, ctk.CTkLabel, ctk.CTkButton, ctk.CTkOptionMenu)):
                    widget.destroy()
            
            # Remove the job from our tracking dictionary
            del self.job_rows[job_id]
            
            # Shift remaining rows up
            for other_job_id, job_data in self.job_rows.items():
                if job_data["row"] > row:
                    job_data["row"] -= 1
                    for widget in job_data.values():
                        if isinstance(widget, (ctk.CTkEntry, ctk.CTkLabel, ctk.CTkButton, ctk.CTkOptionMenu)):
                            widget.grid(row=job_data["row"])
            
            # Update the next available row
            self.next_row -= 1
        else:
            print(f"Warning: Attempted to remove non-existent job with ID {job_id}")

    def open_email_config(self):
        """Open the email configuration dialog."""
        EmailConfigDialog(self, self.config)

if __name__ == "__main__":
    app = HomeScreen()
    app.mainloop()