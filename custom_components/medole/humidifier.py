"""Humidifier platform for Medole Dehumidifier integration."""

import asyncio
import logging

from homeassistant.components.humidifier import (
    HumidifierAction,
    HumidifierDeviceClass,
    HumidifierEntity,
    HumidifierEntityFeature,
)

# No modes from const needed
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pymodbus.client import (
    ModbusSerialClient,
)
from pymodbus.client import ModbusTcpClient
from pymodbus.client import ModbusTcpClient as ModbusRtuOverTcpClient
from pymodbus.exceptions import ModbusException

from .const import (  # REG_TEMPERATURE_1 removed as unused
    CONF_BAUDRATE,
    CONF_BYTESIZE,
    CONF_CONNECTION_TYPE,
    CONF_HOST,
    CONF_PARITY,
    CONF_PORT,
    CONF_SLAVE_ID,
    CONF_STOPBITS,
    CONF_TCP_PORT,
    CONNECTION_TYPE_RTUOVERTCP,
    CONNECTION_TYPE_SERIAL,
    CONTINUOUS_DEHUMIDIFICATION,
    DEFAULT_BAUDRATE,
    DEFAULT_BYTESIZE,
    DEFAULT_PARITY,
    DEFAULT_STOPBITS,
    DEFAULT_TCP_PORT,
    DOMAIN,
    FAN_SPEED_HIGH,
    FAN_SPEED_LOW,
    FAN_SPEED_MEDIUM,
    MAX_HUMIDITY,
    MIN_HUMIDITY,
    REG_DEHUMIDIFY_MODE,
    REG_FAN_SPEED,
    REG_HUMIDITY_1,
    REG_HUMIDITY_SETPOINT,
    REG_OPERATION_STATUS,
    REG_POWER,
    REG_PURIFY_MODE,
    STATUS_COMPRESSOR_ON,
    STATUS_FAN_ON,
)

_LOGGER = logging.getLogger(__name__)

# Create a lock for Modbus connections
MODBUS_LOCK = asyncio.Lock()

# Fan speed mapping for modes
MODES = {
    FAN_SPEED_LOW: "Low",
    FAN_SPEED_MEDIUM: "Medium",
    FAN_SPEED_HIGH: "High",
}

REVERSE_MODES = {v: k for k, v in MODES.items()}


def create_modbus_client(config):
    """Create a modbus client based on configuration."""
    connection_type = config.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_SERIAL)

    if connection_type == CONNECTION_TYPE_SERIAL:
        port = config[CONF_PORT]
        baudrate = config.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)
        bytesize = config.get(CONF_BYTESIZE, DEFAULT_BYTESIZE)
        parity = config.get(CONF_PARITY, DEFAULT_PARITY)
        stopbits = config.get(CONF_STOPBITS, DEFAULT_STOPBITS)

        return ModbusSerialClient(
            port=port,
            baudrate=baudrate,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            timeout=1,
        )

    # Get TCP connection parameters
    host = config[CONF_HOST]
    port = config.get(CONF_TCP_PORT, DEFAULT_TCP_PORT)

    # RTU over TCP
    if connection_type == CONNECTION_TYPE_RTUOVERTCP:
        return ModbusRtuOverTcpClient(
            host=host,
            port=port,
            timeout=1,
            framer="rtu",  # Use RTU framer for RTU over TCP
        )

    # Regular TCP
    return ModbusTcpClient(
        host=host,
        port=port,
        timeout=1,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Medole Dehumidifier humidifier platform."""
    config = config_entry.data

    name = config[CONF_NAME]
    slave_id = config[CONF_SLAVE_ID]

    client = create_modbus_client(config)

    async_add_entities(
        [MedoleDehumidifierHumidifier(name, client, slave_id)],
        True,
    )


class MedoleDehumidifierHumidifier(HumidifierEntity):
    """Representation of a Medole Dehumidifier humidifier device."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = HumidifierEntityFeature.MODES
    _attr_device_class = HumidifierDeviceClass.DEHUMIDIFIER
    _attr_available_modes = list(REVERSE_MODES.keys())
    _attr_min_humidity = MIN_HUMIDITY
    _attr_max_humidity = MAX_HUMIDITY

    def __init__(self, name, client, slave_id):
        """Initialize the humidifier device."""
        self._attr_unique_id = f"{name}_humidifier"
        self._client = client
        self._slave_id = slave_id
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": name,
            "manufacturer": "Medole",
            "model": "IN-D17",
        }

        # Initialize state variables
        self._attr_current_humidity = None
        self._attr_target_humidity = None
        self._attr_mode = None
        self._attr_is_on = False
        self._attr_action = None

    @property
    def current_humidity(self):
        """Return current humidity to set with the ring."""
        return self._attr_current_humidity

    @property
    def target_humidity(self):
        """Return target humidity to set with the ring."""
        return self._attr_target_humidity

    @property
    def min_humidity(self):
        """Return minimum humidity settable with the ring."""
        return self._attr_min_humidity

    @property
    def max_humidity(self):
        """Return maximum humidity settable with the ring."""
        return self._attr_max_humidity

    async def async_update(self):
        """Update the state of the humidifier device."""
        try:
            async with MODBUS_LOCK:
                if not self._client.connect():
                    _LOGGER.error("Failed to connect to Modbus device")
                    return

            # Read power status
            async with MODBUS_LOCK:
                power_result = await self.hass.async_add_executor_job(
                    lambda: self._client.read_holding_registers(
                        REG_POWER, count=1, slave=self._slave_id
                    )
                )

            if power_result.isError():
                _LOGGER.error("Error reading power status")
                return

            power_status = power_result.registers[0]
            self._attr_is_on = power_status == 1

            # Read operation status
            async with MODBUS_LOCK:
                operation_result = await self.hass.async_add_executor_job(
                    lambda: self._client.read_holding_registers(
                        REG_OPERATION_STATUS, count=1, slave=self._slave_id
                    )
                )

            if operation_result.isError():
                _LOGGER.error("Error reading operation status")
                return

            operation_status = operation_result.registers[0]
            compressor_on = operation_status & STATUS_COMPRESSOR_ON
            fan_on = operation_status & STATUS_FAN_ON

            # Determine action based on operation status
            if not self._attr_is_on:
                self._attr_action = HumidifierAction.OFF
            elif compressor_on:
                self._attr_action = HumidifierAction.DRYING
            elif fan_on:
                self._attr_action = HumidifierAction.IDLE
            else:
                self._attr_action = HumidifierAction.IDLE

            # Read dehumidify mode
            async with MODBUS_LOCK:
                dehumidify_result = await self.hass.async_add_executor_job(
                    lambda: self._client.read_holding_registers(
                        REG_DEHUMIDIFY_MODE, count=1, slave=self._slave_id
                    )
                )

            if dehumidify_result.isError():
                _LOGGER.error("Error reading dehumidify mode")
                return

            # Store dehumidify status but not used currently
            _ = dehumidify_result.registers[0]

            # Read purify mode
            async with MODBUS_LOCK:
                purify_result = await self.hass.async_add_executor_job(
                    lambda: self._client.read_holding_registers(
                        REG_PURIFY_MODE, count=1, slave=self._slave_id
                    )
                )

            if purify_result.isError():
                _LOGGER.error("Error reading purify mode")
                return

            # Store purify status but not used currently
            _ = purify_result.registers[0]

            # Read fan speed
            async with MODBUS_LOCK:
                fan_speed_result = await self.hass.async_add_executor_job(
                    lambda: self._client.read_holding_registers(
                        REG_FAN_SPEED, count=1, slave=self._slave_id
                    )
                )

            if fan_speed_result.isError():
                _LOGGER.error("Error reading fan speed")
                return

            fan_speed = fan_speed_result.registers[0]
            self._attr_mode = MODES.get(fan_speed, "Medium")

            # Read current humidity
            async with MODBUS_LOCK:
                humidity_result = await self.hass.async_add_executor_job(
                    lambda: self._client.read_holding_registers(
                        REG_HUMIDITY_1, count=1, slave=self._slave_id
                    )
                )

            if humidity_result.isError():
                _LOGGER.error("Error reading current humidity")
                return

            self._attr_current_humidity = humidity_result.registers[0]

            # Read humidity setpoint
            async with MODBUS_LOCK:
                humidity_setpoint_result = (
                    await self.hass.async_add_executor_job(
                        lambda: self._client.read_holding_registers(
                            REG_HUMIDITY_SETPOINT, count=1, slave=self._slave_id
                        )
                    )
                )

            if humidity_setpoint_result.isError():
                _LOGGER.error("Error reading humidity setpoint")
                return

            humidity_setpoint = humidity_setpoint_result.registers[0]
            if humidity_setpoint == CONTINUOUS_DEHUMIDIFICATION:
                # For continuous mode, set to minimum
                self._attr_target_humidity = MIN_HUMIDITY
            else:
                self._attr_target_humidity = humidity_setpoint

        except ModbusException as ex:
            _LOGGER.error("Error communicating with Modbus device: %s", ex)
        finally:
            self._client.close()

    async def async_set_mode(self, mode: str) -> None:
        """Set new mode."""
        try:
            async with MODBUS_LOCK:
                if not self._client.connect():
                    _LOGGER.error("Failed to connect to Modbus device")
                    return

            fan_speed = REVERSE_MODES.get(mode, FAN_SPEED_MEDIUM)

            async with MODBUS_LOCK:
                await self.hass.async_add_executor_job(
                    lambda: self._client.write_register(
                        REG_FAN_SPEED, fan_speed, slave=self._slave_id
                    )
                )

            self._attr_mode = mode
        except ModbusException as ex:
            _LOGGER.error("Error setting mode: %s", ex)
        finally:
            self._client.close()

    async def async_set_humidity(self, humidity: int) -> None:
        """Set new target humidity."""
        try:
            async with MODBUS_LOCK:
                if not self._client.connect():
                    _LOGGER.error("Failed to connect to Modbus device")
                    return

            # Ensure humidity is within valid range
            humidity = max(MIN_HUMIDITY, min(MAX_HUMIDITY, humidity))

            async with MODBUS_LOCK:
                await self.hass.async_add_executor_job(
                    lambda: self._client.write_register(
                        REG_HUMIDITY_SETPOINT, humidity, slave=self._slave_id
                    )
                )

            self._attr_target_humidity = humidity
        except ModbusException as ex:
            _LOGGER.error("Error setting humidity: %s", ex)
        finally:
            self._client.close()

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the device on."""
        try:
            async with MODBUS_LOCK:
                if not self._client.connect():
                    _LOGGER.error("Failed to connect to Modbus device")
                    return

            # Set power on
            async with MODBUS_LOCK:
                await self.hass.async_add_executor_job(
                    lambda: self._client.write_register(
                        REG_POWER, 1, slave=self._slave_id
                    )
                )

            # Set dehumidify mode on
            async with MODBUS_LOCK:
                await self.hass.async_add_executor_job(
                    lambda: self._client.write_register(
                        REG_DEHUMIDIFY_MODE, 1, slave=self._slave_id
                    )
                )

            # Set purify mode off
            async with MODBUS_LOCK:
                await self.hass.async_add_executor_job(
                    lambda: self._client.write_register(
                        REG_PURIFY_MODE, 0, slave=self._slave_id
                    )
                )

            self._attr_is_on = True
        except ModbusException as ex:
            _LOGGER.error("Error turning device on: %s", ex)
        finally:
            self._client.close()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the device off."""
        try:
            async with MODBUS_LOCK:
                if not self._client.connect():
                    _LOGGER.error("Failed to connect to Modbus device")
                    return

            # Set power off
            async with MODBUS_LOCK:
                await self.hass.async_add_executor_job(
                    lambda: self._client.write_register(
                        REG_POWER, 0, slave=self._slave_id
                    )
                )

            self._attr_is_on = False
        except ModbusException as ex:
            _LOGGER.error("Error turning device off: %s", ex)
        finally:
            self._client.close()
