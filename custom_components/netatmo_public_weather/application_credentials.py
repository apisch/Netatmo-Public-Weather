"""Application credentials platform for Netatmo Public Weather."""

from homeassistant.components.application_credentials import AuthorizationServer
from homeassistant.core import HomeAssistant

from .const import OAUTH2_AUTHORIZE, OAUTH2_TOKEN


async def async_get_authorization_server(hass: HomeAssistant) -> AuthorizationServer:
    """Return the Netatmo authorization server."""
    return AuthorizationServer(authorize_url=OAUTH2_AUTHORIZE, token_url=OAUTH2_TOKEN)


async def async_get_description_placeholders(hass: HomeAssistant) -> dict[str, str]:
    """Return placeholders for the credentials dialog."""
    return {
        "developer_url": "https://dev.netatmo.com/apps/",
        "redirect_url": "https://my.home-assistant.io/redirect/oauth",
        "docs_url": "https://github.com/apisch/Netatmo-Public-Weather/blob/main/docs/netatmo-app.md",
    }
