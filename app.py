import os, secrets, requests
from urllib.parse import urlencode
from flask import Flask, redirect, request, session
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
@app.before_request
def force_localhost():
    if request.host.startswith("127.0.0.1"):
        return redirect(request.url.replace("127.0.0.1", "localhost", 1))
app.secret_key = os.environ["SECRET_KEY"]
app.config["SESSION_COOKIE_NAME"] = "spy_session"

CLIENT_ID = os.environ["GITHUB_CLIENT_ID"]
CLIENT_SECRET = os.environ["GITHUB_CLIENT_SECRET"]
REDIRECT_URI = "http://localhost:5000/callback"

@app.route("/")
def home():
    user = session.get("user")
    if user:
        return f"""
        <h1>Welcome, Agent {user['name'] or user['login']}</h1>
        <p>Email: {user['email']}</p>
        <img src="{user['avatar_url']}" width="100"><br><br>
        <a href="/logout">Logout</a>"""
    return '<h1>Secret Agent Portal</h1><a href="/login"><button>Login with GitHub</button></a>'

@app.route("/login")
def login():
    state = secrets.token_urlsafe(16)          # CSRF protection
    session["oauth_state"] = state
    params = urlencode({
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "read:user user:email",
        "state": state,
    })
    return redirect(f"https://github.com/login/oauth/authorize?{params}")

@app.route("/callback")
def callback():
    # 1. Verify state
    if request.args.get("state") != session.pop("oauth_state", None):
        return "Invalid state - possible CSRF attack", 400

    code = request.args.get("code")
    if not code:
        return "Authorization denied", 400

    # 2. Exchange authorization code for access token
    token_res = requests.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
    ).json()
    access_token = token_res.get("access_token")
    if not access_token:
        return f"Token error: {token_res}", 400

    # 3. Log the token securely (masked)
    print(f"[+] Access token received: {access_token[:4]}...{access_token[-4:]}")
    print(f"[+] Scope: {token_res.get('scope')} | Type: {token_res.get('token_type')}")

    # 4. Use the token to call the API
    headers = {"Authorization": f"Bearer {access_token}"}
    user = requests.get("https://api.github.com/user", headers=headers).json()

    # Email may be private, so fetch it separately
    if not user.get("email"):
        emails = requests.get("https://api.github.com/user/emails", headers=headers).json()
        user["email"] = next((e["email"] for e in emails if e.get("primary")), "Not available")

    session["user"] = {k: user.get(k) for k in ("login", "name", "email", "avatar_url")}
    return redirect("/")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(port=5000, debug=True)