"""
Sends alert emails via Gmail SMTP using an App Password (not your real Gmail
password — see README for how to generate one). No third-party email vendor
needed, which keeps this to one fewer credential to manage.
"""

import os
import smtplib
from email.mime.text import MIMEText

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")


def send_alert_email(to_email: str, talent_name: str, risk_flag: str, reason: str, recommended_action: str) -> bool:
    """Returns True if the email was sent, False if email isn't configured
    (missing env vars) or sending failed — callers should not crash the
    recheck loop over a single failed email."""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        return False

    subject = f"Likeness Watch: new activity for {talent_name} [{risk_flag.upper()}]"
    body = (
        f"New activity found for {talent_name}.\n\n"
        f"Risk level: {risk_flag.upper()}\n"
        f"{reason}\n\n"
        f"Recommended action:\n{recommended_action}\n\n"
        f"Log in to Likeness Watch to see full sources and citations."
    )

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = to_email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, [to_email], msg.as_string())
        return True
    except Exception:
        return False
