"""Create (or reset the password of) a local account — F01.

The only way to get the *first* administrator when the API runs with
BISCUITS_AUTH_MODE=login, since there is no public signup and creating accounts
over HTTP requires an admin session. Later accounts can be created from the
console (page Entreprise) or with this script too.

    python -m scripts.create_user --email alice@example.com --name "Alice" --role admin
    python -m scripts.create_user --email alice@example.com --reset-password

The password is prompted (never taken from argv, so it doesn't land in the shell
history or the process list). Uses the same BISCUITS_ENTERPRISE_DB as the API.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from api.enterprise import ROLES, store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default=None)
    parser.add_argument("--role", choices=sorted(ROLES, key=ROLES.get), default="admin")
    parser.add_argument("--reset-password", action="store_true", help="change the password of an existing account")
    args = parser.parse_args(argv)

    password = getpass.getpass("Mot de passe (10 caractères minimum) : ")
    if password != getpass.getpass("Confirme le mot de passe : "):
        print("Les deux saisies diffèrent.", file=sys.stderr)
        return 2

    existing = next((u for u in store.users() if u["email"] == args.email.strip().lower()), None)
    if args.reset_password:
        if existing is None:
            print(f"Aucun compte pour {args.email}", file=sys.stderr)
            return 1
        store.update_user(existing["id"], password=password)
        store.audit("cli", "auth.user.updated", "user", existing["id"], None, {"password_reset": True})
        print(f"Mot de passe de {existing['email']} mis à jour (toutes ses sessions sont fermées).")
        return 0

    user = store.create_user(args.email, args.name or args.email, args.role, password)
    store.audit("cli", "auth.user.created", "user", user["id"], None, {"email": user["email"], "role": user["role"]})
    print(f"Compte {user['role']} créé pour {user['email']} ({user['id']}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
