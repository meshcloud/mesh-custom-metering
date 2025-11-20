import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os


def send_email(
    sender_email, app_password, to_email, subject, body, attachments=None, is_html=False
):
    """
    Send email using Gmail SMTP with App Password

    Args:
        sender_email (str): Your Gmail address
        app_password (str): Your 16-character App password
        to_email (str or list): Recipient email(s)
        subject (str): Email subject
        body (str): Email body content
        attachments (list): List of file paths to attach (optional)
        is_html (bool): Whether body content is HTML

    Returns:
        bool: True if sent successfully, False otherwise
    """
    try:
        # Create message
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = to_email if isinstance(to_email, str) else ", ".join(to_email)
        msg["Subject"] = subject

        # Add body to email
        if is_html:
            msg.attach(MIMEText(body, "html"))
        else:
            msg.attach(MIMEText(body, "plain"))

        # Add attachments if provided
        if attachments:
            for file_path in attachments:
                if os.path.isfile(file_path):
                    with open(file_path, "rb") as attachment:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(attachment.read())

                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f"attachment; filename= {os.path.basename(file_path)}",
                    )
                    msg.attach(part)

        # Gmail SMTP configuration
        smtp_server = "smtp.gmail.com"
        smtp_port = 587

        # Create SMTP session
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # Enable security
        server.login(sender_email, app_password)

        # Send email
        text = msg.as_string()
        server.sendmail(sender_email, to_email, text)
        server.quit()

        logging.info(f"Email sent successfully to {to_email}")
        return True

    except Exception as e:
        logging.error(f"Error sending email: {str(e)}")
        return False
