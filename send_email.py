"""
Emails today's report with the tide chart shown in the email itself.

Sends through Gmail. Needs a Gmail "app password" saved in the repo as a
secret called GMAIL_APP_PASSWORD (Settings > Secrets and variables > Actions).
If that secret isn't there, this does nothing and the GitHub issue email is
used instead.
"""

import os
import sys
import smtplib
from email.message import EmailMessage

import markdown

password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
sender = os.environ.get("MAIL_FROM", "")
to = os.environ.get("MAIL_TO", "")

if not password or not sender or not to:
    print("No Gmail app password set - skipping direct email.")
    sys.exit(0)

title = open("title.txt").read().strip()
report = open("REPORT.md").read()

# Find the chart line, take it out of the text and attach the image inline.
chart_path = None
lines = []
for line in report.splitlines():
    if line.startswith("![") and "](charts/" in line:
        chart_path = line.split("](", 1)[1].rstrip(")")
        lines.append("CHART_HERE")
    else:
        lines.append(line)

html = markdown.markdown("\n".join(lines))
if chart_path and os.path.exists(chart_path):
    html = html.replace("<p>CHART_HERE</p>",
                        '<p><img src="cid:tidechart" alt="Tide chart" '
                        'style="max-width:100%;height:auto;"></p>')
else:
    html = html.replace("<p>CHART_HERE</p>", "")

body = f"""<div style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;
color:#0f2b30;max-width:680px">{html}</div>"""

msg = EmailMessage()
msg["Subject"] = title
msg["From"] = f"Fishing checker <{sender}>"
msg["To"] = to
msg.set_content(report)  # plain-text fallback
msg.add_alternative(body, subtype="html")

if chart_path and os.path.exists(chart_path):
    with open(chart_path, "rb") as f:
        msg.get_payload()[1].add_related(f.read(), maintype="image",
                                         subtype="png", cid="<tidechart>")

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
    s.login(sender, password)
    s.send_message(msg)

print(f"Emailed {to}")
