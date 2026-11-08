"""Resolve [%key:...%] references in strings.json into translations/en.json.

Home Assistant only resolves these references for core integrations, so a
custom integration has to ship resolved files. Run after editing strings.json:

    python3 scripts/build_translations.py
"""

from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent / "custom_components" / "netatmo_public_weather"

COMMON = {
    "common::config_flow::title::oauth2_pick_implementation": "Pick authentication method",
    "common::config_flow::title::reauth": "Authentication expired",
    "common::config_flow::abort::already_configured_account": "Account is already configured",
    "common::config_flow::abort::oauth2_missing_configuration": "The integration is not configured. Please add application credentials first.",
    "common::config_flow::abort::oauth2_authorize_url_timeout": "Timeout generating authorize URL.",
    "common::config_flow::abort::oauth2_no_url_available": "No URL available. For information about this error, check the help section.",
    "common::config_flow::abort::oauth2_error": "Received invalid token data.",
    "common::config_flow::abort::oauth2_timeout": "Timeout resolving OAuth token.",
    "common::config_flow::abort::oauth2_unauthorized": "OAuth authorization error while obtaining access token.",
    "common::config_flow::abort::oauth2_failed": "Error while obtaining access token.",
    "common::config_flow::abort::oauth2_user_rejected_authorize": "Account linking rejected.",
    "common::config_flow::abort::reauth_successful": "Re-authentication was successful",
    "common::config_flow::create_entry::authenticated": "Successfully authenticated",
}
REF = re.compile(r"^\[%key:([^%]+)%\]$")


def _lookup(strings: dict, ref: str) -> str:
    if ref in COMMON:
        return COMMON[ref]
    prefix = "component::netatmo_public_weather::"
    if not ref.startswith(prefix):
        raise KeyError(f"Unknown reference {ref}")
    node = strings
    for part in ref[len(prefix):].split("::"):
        node = node[part]
    return _resolve(strings, node)


def _resolve(strings: dict, node):
    if isinstance(node, dict):
        return {k: _resolve(strings, v) for k, v in node.items()}
    if isinstance(node, str) and (m := REF.match(node)):
        return _lookup(strings, m.group(1))
    return node


def main() -> None:
    strings = json.loads((ROOT / "strings.json").read_text())
    resolved = _resolve(strings, strings)
    (ROOT / "translations" / "en.json").write_text(json.dumps(resolved, indent=2, ensure_ascii=False) + "\n")
    print("translations/en.json written")


if __name__ == "__main__":
    main()
