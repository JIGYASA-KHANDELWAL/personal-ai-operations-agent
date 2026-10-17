
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


def draft_email(purpose, recipient, tone="Professional"):
    prompt = f"""
You are an email drafting assistant.

Draft a clear, useful email using the details below.

Purpose: {purpose}
Recipient: {recipient}
Tone: {tone}

Return the result in this format:

SUBJECT: [email subject]

BODY:
[email body]

Do not invent dates, names, commitments, or facts.
Use placeholders where necessary.
Do not send the email.
"""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt
    )

    return response.text


if __name__ == "__main__":
    purpose = input("What is the email about? ").strip()
    recipient = input("Who is the recipient? ").strip()

    if not purpose or not recipient:
        print("Please enter both the purpose and recipient.")
    else:
        print("\n--- EMAIL DRAFT ---\n")
        print(draft_email(purpose, recipient))
