import imaplib
import email
from email.header import decode_header
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import os
from git import Repo
from msal import PublicClientApplication, ConfidentialClientApplication
import msal
import json
import base64
import requests


# Email credentials and server


def get_graph_ql_access_token():
        
    # 1. Create the public client application
    app = msal.PublicClientApplication(client_id=CLIENT_ID, authority=AUTHORITY)

    # 2. Initiate device code flow
    flow = app.initiate_device_flow(scopes=SCOPES)

    if 'user_code' not in flow:
        raise ValueError("Failed to create device flow")

    print(f"Please go to {flow['verification_uri']} and enter the code: {flow['user_code']}")

    # 3. Wait for user to authenticate
    result = app.acquire_token_by_device_flow(flow)

    if 'access_token' not in result:
        raise Exception("Authentication failed: " + result.get("error_description", "No error description"))

    return result['access_token']

def fetch_emails(access_token, email_account, top_n=10):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Use mailFolders/Inbox to target the actual inbox
    url = f"https://graph.microsoft.com/v1.0/users/{EMAIL_ACCOUNT}/mailFolders/{MAILBOX_ID}/messages?$top={top_n}"

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch emails: {response.status_code} {response.text}")

    data = response.json()
    emails = []

    for item in data.get("value", []):
        email_id = item.get("id")
        email_obj = {
            "subject": item.get("subject"),
            "body": item.get("body"),  # Keep full body object
            "id": email_id,
            "dateReceived": item.get("receivedDateTime")
        }

        # Mark as read
        mark_as_read_url = f"https://graph.microsoft.com/v1.0/users/{email_account}/messages/{email_id}"
        patch_resp = requests.patch(
            mark_as_read_url,
            headers=headers,
            json={"isRead": True}
        )
        if patch_resp.status_code not in (200, 204):
            print(f"Failed to mark as read for email ID {email_id}: {patch_resp.status_code}, {patch_resp.text}")

        emails.append(email_obj)

    return emails

def get_or_update_repo(branch):
    if not os.path.exists(REPO_LOCAL_PATH):
        print("Cloning repository...")
        repo = Repo.clone_from(
            REPO_URL.replace("https://", f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@"),
            REPO_LOCAL_PATH,
            branch=branch,
            single_branch=True,
        )
    else:
        repo = Repo(REPO_LOCAL_PATH)
        repo.git.checkout(branch)
        repo.remotes.origin.pull()
    return repo

def save_markdown_to_repo(repo, filename, markdown, branch):
    filepath = os.path.join(REPO_LOCAL_PATH, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(markdown)

    repo.git.add(filename)
    repo.index.commit(f"Add email markdown: {filename}")
    repo.remotes.origin.push(refspec=f"{branch}:{branch}")
    print(f"Pushed {filename} to branch {branch}")

def main():
    token = get_graph_ql_access_token()
    emails = fetch_emails(token, EMAIL_ACCOUNT)
    print(f"Fetched {len(emails)} emails.")

    repo = get_or_update_repo(GITHUB_BRANCH)

    for msg in emails:
        subject = msg["subject"] or "untitled"
        body_obj = msg.get("body", {})
        date_received = msg.get("dateReceived", "").replace(":", "-")
        content_type = body_obj.get("contentType", "").lower()
        content = body_obj.get("content", "")

        if content_type == "html":
            markdown = md(content)
        elif content_type == "text":
            markdown = content.strip()
        else:
            markdown = "No usable content found."

        print(f"Processing email: {subject}")
        filename = subject.replace(" ", "_").replace("/", "_") + f"{date_received}.md"
        save_markdown_to_repo(repo, filename, markdown, branch=GITHUB_BRANCH)
        
if __name__ == "__main__":
    main()
