"""
Doc inbox Hotmail/Outlook tu refresh_token hang loat
su dung Microsoft Graph API (thay vi IMAP).

Input format moi dong:
email|password|refresh_token|client_id

Luu y:
- Truong password duoc giu de tuong thich format, script KHONG su dung password.
- Su dung Graph API endpoint https://graph.microsoft.com/v1.0/me/messages
  thay cho IMAP vi nhieu consumer Hotmail account bi chan IMAP.
"""

from __future__ import annotations

import argparse
import sys
from typing import Dict, List, Tuple

from graph_api_service import exchange_refresh_token, get_messages

def read_latest_messages(
    token_info: Dict[str, str], limit: int = 5
) -> Tuple[bool, List[Dict] | str]:
    """Doc N mail moi nhat tu mail API phu hop voi token da exchange."""
    return get_messages(token_info, limit=limit)


def read_latest_subjects(
    email_addr: str, token_info: Dict[str, str], limit: int = 5
) -> Tuple[bool, List[str] | str]:
    """Wrapper tuong thich voi UI cu - tra ve list subject strings."""
    ok, data = read_latest_messages(token_info, limit=limit)
    if not ok:
        return False, data
    
    if not data:
        return True, ["(Inbox trong)"]
    
    subjects = []
    for msg in data:
        subj = msg["subject"] or "(no subject)"
        subjects.append(subj)
    
    return True, subjects


def parse_input_lines(raw: str) -> List[Dict[str, str]]:
    accounts: List[Dict[str, str]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) < 4:
            print(f"[SKIP] Sai format: {line[:80]}")
            continue

        accounts.append(
            {
                "email": parts[0].strip(),
                "password": parts[1].strip(),
                "refresh_token": parts[2].strip(),
                "client_id": parts[3].strip(),
            }
        )
    return accounts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Doc inbox tu refresh_token Hotmail/Outlook (Graph API)"
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="File txt, moi dong: email|password|refresh_token|client_id",
    )
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=5,
        help="So mail moi nhat can doc moi account (mac dinh: 5)",
    )
    args = parser.parse_args()

    try:
        with open(args.input, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except Exception as exc:
        print(f"Khong mo duoc file input: {exc}")
        return 1

    accounts = parse_input_lines(raw)
    if not accounts:
        print("Khong co account hop le.")
        return 1

    print(f"Tong account hop le: {len(accounts)}")
    print("-" * 80)

    for idx, acc in enumerate(accounts, start=1):
        email_addr = acc["email"]
        refresh_token = acc["refresh_token"]
        client_id = acc["client_id"]

        ok_token, token_or_err = exchange_refresh_token(refresh_token, client_id)
        if not ok_token:
            print(f"[{idx}] {email_addr} -> FAIL token: {token_or_err}")
            print("-" * 80)
            continue

        ok_inbox, inbox_data = read_latest_subjects(
            email_addr, token_or_err, limit=max(1, args.limit)
        )
        if not ok_inbox:
            print(f"[{idx}] {email_addr} -> FAIL inbox: {inbox_data}")
            print("-" * 80)
            continue

        print(f"[{idx}] {email_addr} -> OK")
        for i, subject in enumerate(inbox_data, start=1):
            print(f"  {i}. {subject}")
        print("-" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
