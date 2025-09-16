# stub implementations

def generate_password_reset_token(email: str) -> str:
    return "signed-token"

def verify_password_reset_token(token: str) -> str | None:
    return "user@example.com"

def generate_reset_password_email(email_to: str, email: str, token: str):
    class E:
        subject      = "Reset your password"
        html_content = f"<p>Reset link: ?token={token}</p>"
    return E()

def send_email(email_to: str, subject: str, html_content: str):
    pass
