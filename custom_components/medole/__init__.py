"""The Medole Dehumidifier integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_SLAVE_ID, DOMAIN
from .modbus import create_modbus_client

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.HUMIDIFIER, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Medole Dehumidifier from a config entry."""
    config = entry.data

    # Create the Modbus client once
    client = create_modbus_client(config)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "config": config,
        "slave_id": config[CONF_SLAVE_ID],
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
