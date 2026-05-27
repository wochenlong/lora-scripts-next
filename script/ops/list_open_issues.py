import json, os, urllib.request
token = os.environ.get("GITHUB_TOKEN") or __import__("winreg").QueryValueEx(
    __import__("winreg").OpenKey(__import__("winreg").HKEY_CURRENT_USER, "Environment"), "GITHUB_TOKEN"
)[0]
req = urllib.request.Request(
    "https://api.github.com/repos/wochenlong/lora-scripts-next/issues?state=open&per_page=100",
    headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    },
)
with urllib.request.urlopen(req) as r:
    issues = json.loads(r.read())
for i in issues:
    if "pull_request" in i:
        continue
    labels = ",".join(l["name"] for l in i.get("labels", []))
    print(f"{i['number']}\t{labels}\t{i['title']}")
