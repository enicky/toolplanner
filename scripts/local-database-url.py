#!/usr/bin/env python3
import json
import sys
from urllib.parse import urlsplit, urlunsplit


configuration = json.load(sys.stdin)
database_url = configuration["services"]["api"]["environment"]["TOOLPLANNER_DATABASE_URL"]
parts = urlsplit(database_url)

if parts.hostname == "postgres":
    published_port = next(
        int(port["published"])
        for port in configuration["services"]["postgres"]["ports"]
        if int(port["target"]) == 5432
    )
    user_info, separator, _ = parts.netloc.rpartition("@")
    host = f"127.0.0.1:{published_port}"
    netloc = f"{user_info}{separator}{host}" if separator else host
    database_url = urlunsplit(
        (parts.scheme, netloc, parts.path, parts.query, parts.fragment)
    )

print(database_url)
