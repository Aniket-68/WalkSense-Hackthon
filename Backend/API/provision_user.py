"""
Managed user provisioning utility.

Usage:
    cd Backend
    python3 -m API.provision_user --username admin2 --password 'StrongPass!234'
    python3 -m API.provision_user --username admin2 --password 'NewPass!234' --update
"""

from __future__ import annotations

import argparse
import getpass
import sys

from API.auth import provision_managed_user


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision/update WalkSense auth users")
    parser.add_argument("--username", required=True, help="Username to create/update")
    parser.add_argument("--password", help="Password for the user (if omitted, prompt securely)")
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update existing user if already present",
    )
    parser.add_argument(
        "--inactive",
        action="store_true",
        help="Create/update user as inactive",
    )
    args = parser.parse_args()

    password = args.password or getpass.getpass("Password: ")
    if not password:
        print("Password cannot be empty", file=sys.stderr)
        return 2

    try:
        result = provision_managed_user(
            args.username,
            password,
            is_active=not args.inactive,
            force_update=args.update,
        )
    except Exception as exc:
        print(f"Provisioning failed: {exc}", file=sys.stderr)
        return 1

    action = "created" if result["created"] else "updated"
    print(f"User {action}: {result['username']} (id={result['id']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
