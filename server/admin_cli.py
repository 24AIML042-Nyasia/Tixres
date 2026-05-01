#!/usr/bin/env python3
"""admin_cli.py – Tixres administrator command-line tool.

Usage examples
--------------
  python admin_cli.py create-admin  --username alice --password secret123
  python admin_cli.py create-user   --username bob   --password pass456
  python admin_cli.py list-users
  python admin_cli.py assign-agent  --username bob   --hostname WORKSTATION-01
  python admin_cli.py unassign-agent --username bob  --hostname WORKSTATION-01
  python admin_cli.py list-assignments
  python admin_cli.py delete-user   --username bob
  python admin_cli.py issue-token   --username alice
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from the server/ directory or the project root
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from auth import AuthStore, issue_token  # noqa: E402


def _store() -> AuthStore:
    s = AuthStore()
    s.init_db()
    return s


def cmd_create_admin(args: argparse.Namespace) -> None:
    store = _store()
    ok = store.create_user(args.username, args.password, role="admin")
    if ok:
        print(f"✓ Admin '{args.username}' created.")
    else:
        print(f"✗ Username '{args.username}' already exists.", file=sys.stderr)
        sys.exit(1)


def cmd_create_user(args: argparse.Namespace) -> None:
    store = _store()
    ok = store.create_user(args.username, args.password, role="user")
    if ok:
        print(f"✓ User '{args.username}' created.")
    else:
        print(f"✗ Username '{args.username}' already exists.", file=sys.stderr)
        sys.exit(1)


def cmd_list_users(args: argparse.Namespace) -> None:
    store = _store()
    users = store.list_users()
    if not users:
        print("No users found.")
        return
    print(f"{'Username':<20} {'Role':<8} {'Active':<8} {'Created'}")
    print("-" * 60)
    for u in users:
        active = "yes" if u["is_active"] else "no"
        print(f"{u['username']:<20} {u['role']:<8} {active:<8} {u['created_at']}")


def cmd_delete_user(args: argparse.Namespace) -> None:
    store = _store()
    ok = store.delete_user(args.username)
    if ok:
        print(f"✓ User '{args.username}' deleted.")
    else:
        print(f"✗ User '{args.username}' not found.", file=sys.stderr)
        sys.exit(1)


def cmd_assign_agent(args: argparse.Namespace) -> None:
    store = _store()
    user = store.get_user(args.username)
    if not user:
        print(f"✗ User '{args.username}' not found.", file=sys.stderr)
        sys.exit(1)
    ok = store.assign_agent(args.username, args.hostname)
    if ok:
        print(f"✓ Hostname '{args.hostname}' assigned to user '{args.username}'.")
    else:
        print(f"  Hostname '{args.hostname}' was already assigned to '{args.username}'.")


def cmd_unassign_agent(args: argparse.Namespace) -> None:
    store = _store()
    ok = store.unassign_agent(args.username, args.hostname)
    if ok:
        print(f"✓ Assignment removed: '{args.hostname}' ← '{args.username}'.")
    else:
        print(f"✗ No such assignment found.", file=sys.stderr)
        sys.exit(1)


def cmd_list_assignments(args: argparse.Namespace) -> None:
    store = _store()
    assignments = store.list_assignments()
    if not assignments:
        print("No assignments found.")
        return
    print(f"{'Username':<20} {'Hostname':<30} {'Assigned At'}")
    print("-" * 70)
    for a in assignments:
        print(f"{a['username']:<20} {a['hostname']:<30} {a['assigned_at']}")


def cmd_issue_token(args: argparse.Namespace) -> None:
    store = _store()
    user = store.get_user(args.username)
    if not user:
        print(f"✗ User '{args.username}' not found.", file=sys.stderr)
        sys.exit(1)
    secret = store.get_secret()
    token = issue_token(args.username, user["role"], secret)
    print(f"Token for '{args.username}' (role={user['role']}):")
    print(token)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tixres Admin CLI – manage users and agent assignments."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # create-admin
    p = sub.add_parser("create-admin", help="Create an admin UI user (Admin only via CLI)")
    p.add_argument("--username", required=True)
    p.add_argument("--password", required=True)

    # create-user
    p = sub.add_parser("create-user", help="Create a regular UI user")
    p.add_argument("--username", required=True)
    p.add_argument("--password", required=True)

    # list-users
    sub.add_parser("list-users", help="List all UI users")

    # delete-user
    p = sub.add_parser("delete-user", help="Delete a UI user")
    p.add_argument("--username", required=True)

    # assign-agent
    p = sub.add_parser("assign-agent", help="Assign an agent hostname to a user")
    p.add_argument("--username", required=True)
    p.add_argument("--hostname", required=True)

    # unassign-agent
    p = sub.add_parser("unassign-agent", help="Remove agent assignment from a user")
    p.add_argument("--username", required=True)
    p.add_argument("--hostname", required=True)

    # list-assignments
    sub.add_parser("list-assignments", help="List all agent–user assignments")

    # issue-token
    p = sub.add_parser("issue-token", help="Issue a JWT for a user (for testing)")
    p.add_argument("--username", required=True)

    args = parser.parse_args()
    dispatch = {
        "create-admin": cmd_create_admin,
        "create-user": cmd_create_user,
        "list-users": cmd_list_users,
        "delete-user": cmd_delete_user,
        "assign-agent": cmd_assign_agent,
        "unassign-agent": cmd_unassign_agent,
        "list-assignments": cmd_list_assignments,
        "issue-token": cmd_issue_token,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
