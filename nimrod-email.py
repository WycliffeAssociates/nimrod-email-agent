from markdownify import markdownify as md
import os
from git import Repo
from msal import ConfidentialClientApplication
import requests


# Email credentials and server
EMAIL_ACCOUNT = os.getenv("EMAIL_ACCOUNT")
MAILBOX_ID = os.getenv("MAILBOX_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REPO_URL = os.getenv("REPO_URL")
REPO_LOCAL_PATH = os.getenv("REPO_LOCAL_PATH")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH")

AUTHORITY = f'https://login.microsoftonline.com/{TENANT_ID}'
SCOPE = ["https://graph.microsoft.com/.default"]  # For app-only token

def get_access_token():
    app = ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=AUTHORITY
    )

    result = app.acquire_token_for_client(scopes=SCOPE)
    return result["access_token"]


def fetch_emails(access_token, top_n=10):
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
    token = get_access_token()
    emails = fetch_emails(token)
    print(f"Fetched {len(emails)} emails.")
    for email in emails:
        print(f"EmailID: {email['id']}")

    repo = get_or_update_repo(GITHUB_BRANCH)

    for msg in emails:
        id = msg["id"]
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
        filename = subject.replace(" ", "_").replace("/", "_") + f"{date_received}#{id}.md"
        save_markdown_to_repo(repo, filename, markdown, branch=GITHUB_BRANCH)
        
if __name__ == "__main__":
    main()
