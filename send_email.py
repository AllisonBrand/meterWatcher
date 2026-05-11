# from smtplib import SMTP
import smtplib
from email.message import EmailMessage
from env_vars import APP_PASSWORD

DEBUG_MODE = True
GMAIL_ADDR = 'meterWatcher@gmail.com'

def send(subject, body, receive_addr, body_html = True):
  '''Send an email using Secure SMTP.'''
  if DEBUG_MODE: print("Starting to send email")
  try:
    with smtplib.SMTP('smtp.gmail.com', 587, timeout=5) as smtp:
      smtp.starttls()
      if DEBUG_MODE: print("Entered TLS mode")
      # smtp.ehlo()
      smtp.login(GMAIL_ADDR, APP_PASSWORD)
      if DEBUG_MODE: print("Logged in.")   
      msg = EmailMessage()
      msg['Subject'] = subject
      msg['From'] = GMAIL_ADDR
      msg['To'] = receive_addr  
      msg.set_content(body, subtype='html')
      # msg = f'Subject: {subject}\n\n{body}'
      smtp.send_message(from_addr=GMAIL_ADDR, to_addrs=receive_addr, msg=msg) 
    print('Sent successfully!')
  except Exception as e:
    smtp.quit() 
    print(F'An error occurred: {e}')

if __name__ == "__main__":  send("This is the subject", "Body", GMAIL_ADDR)