"""Preconfigure the local server and credentials before pgAdmin starts."""
import json
import os
from pathlib import Path


def pgpass_escape(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("Database connection values must not contain line breaks")
    return value.replace("\\", "\\\\").replace(":", "\\:")


def configure() -> None:
    email = os.environ["PGADMIN_DEFAULT_EMAIL"]
    host = os.environ.get("DB_HOST", "db")
    port = os.environ.get("DB_PORT", "5432")
    database = os.environ["POSTGRES_DB"]
    username = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]

    # pgAdmin server-mode file paths are relative to this user's storage.
    storage = Path("/var/lib/pgadmin/storage") / email.replace("@", "_")
    storage.mkdir(parents=True, exist_ok=True)
    passfile = storage / ".pgpass"
    os.umask(0o077)
    passfile.write_text(
        ":".join(pgpass_escape(v) for v in (host, port, "*", username, password)) + "\n",
        encoding="utf-8",
    )
    passfile.chmod(0o600)

    servers = {"Servers": {"1": {
        "Name": "Fintech local",
        "Group": "Desarrollo",
        "Host": host,
        "Port": int(port),
        "MaintenanceDB": database,
        "Username": username,
        "ConnectionParameters": {
            "sslmode": "prefer",
            "connect_timeout": 5,
            "passfile": ".pgpass",
        },
    }}}
    server_file = Path("/tmp/fintech-servers.json")
    server_file.write_text(json.dumps(servers), encoding="utf-8")
    os.environ["PGADMIN_SERVER_JSON_FILE"] = str(server_file)


if __name__ == "__main__":
    configure()
    os.execv("/entrypoint.sh", ["/entrypoint.sh"])
