"""F5 bootstrap: create the initial ADMIN operator.

PromptID: ADMS-Frontend-F5-Auth-001

Run inside the API container (or with DB env reachable):

    python -m app.api.bootstrap_admin --username admin --password '<strong>'

Refuses to run when any operator already exists (idempotent safety — the
first ADMIN is bootstrapped exactly once via CLI, never from env).
"""

import argparse
import getpass
import sys

from app.api.auth import hash_password
from app.api.dependencies import get_cfg
from app.db import get_db_connection


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the initial ADMIN operator (F5).")
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", default="ADMS Administrator")
    parser.add_argument("--password", default=None, help="omit to prompt securely")
    args = parser.parse_args()

    password = args.password
    if not password:
        password = getpass.getpass("ADMIN password: ")
    if len(password) < 12:
        print("ERROR: password must be at least 12 characters", file=sys.stderr)
        return 1

    cfg = get_cfg()
    try:
        with get_db_connection(cfg) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM operators LIMIT 1;")
                if cur.fetchone() is not None:
                    print("ERROR: an operator already exists — bootstrap is one-time only", file=sys.stderr)
                    return 1
                password_hash = hash_password(password)
                cur.execute(
                    "INSERT INTO operators (username, display_name, role, password_hash) "
                    "VALUES (%s, %s, 'ADMIN', %s) RETURNING operator_id;",
                    (args.username, args.display_name, password_hash),
                )
                row = cur.fetchone()
                conn.commit()
    except Exception as e:
        print("ERROR: bootstrap failed: %s" % e, file=sys.stderr)
        return 1

    print("OK: ADMIN operator '%s' created (operator_id=%s)" % (args.username, row[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
