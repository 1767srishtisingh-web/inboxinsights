#!/usr/bin/env python3
"""
Creates github_secrets.txt containing the 4 values you paste into
GitHub -> Settings -> Secrets and variables -> Actions.

Run from the project folder AFTER `python main.py` has worked on your laptop:
    python tools/make_github_secrets.py

DELETE github_secrets.txt after you have copied the values. It contains
your passwords and Gmail access.
"""
import base64
import io
import os
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

needed = [".env", "credentials.json", os.path.join("users", "users.json"), "tokens"]
missing = [p for p in needed if not os.path.exists(p)]
if missing:
    sys.exit("Missing: " + ", ".join(missing) +
             "\nFinish the laptop setup and run `python main.py` successfully first.")
if not [f for f in os.listdir("tokens") if f.endswith("_token.json")]:
    sys.exit("The tokens folder is empty. Run `python main.py` and log in to each Gmail first.")

def read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read().strip()

buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tar:
    tar.add("tokens", arcname="tokens")
tokens_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

secrets = [
    ("APP_ENV", read(".env")),
    ("GMAIL_CREDENTIALS_JSON", read("credentials.json")),
    ("USERS_JSON", read(os.path.join("users", "users.json"))),
    ("GMAIL_TOKENS_B64", tokens_b64),
]

with open("github_secrets.txt", "w", encoding="utf-8") as out:
    out.write("Create one GitHub secret for each block below.\n")
    out.write("Name = the text after 'SECRET NAME:'. Value = everything between the lines.\n")
    out.write("DELETE THIS FILE WHEN DONE.\n\n")
    for name, value in secrets:
        out.write(f"SECRET NAME: {name}\n")
        out.write("-" * 60 + "\n")
        out.write(value + "\n")
        out.write("-" * 60 + "\n\n")

print("Done. Open github_secrets.txt (in the project folder) and copy each value into GitHub.")
print("Remember to delete github_secrets.txt afterwards.")
