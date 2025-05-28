"""Sensor platform for Medole Dehumidifier integration."""

import asyncio
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pymodbus.client import ModbusSerialClient, ModbusTcpClient
from pymodbus.exceptions import ModbusException

from .const import (
    CONF_BAUDRATE,
    CONF_BYTESIZE,
    CONF_CONNECTION_TYPE,
    CONF_HOST,
    CONF_PARITY,
    CONF_PORT,
    CONF_SLAVE_ID,
    CONF_STOPBITS,
    CONF_TCP_PORT,
    CONNECTION_TYPE_SERIAL,
    DEFAULT_BAUDRATE,
    DEFAULT_BYTESIZE,
    DEFAULT_PARITY,
    DEFAULT_STOPBITS,
    DEFAULT_TCP_PORT,
    DOMAIN,
    REG_FAN_ALARM_HOURS,
    REG_FAN_OPERATION_HOURS,
    REG_HUMIDITY_1,
    REG_HUMIDITY_2,
    REG_OPERATION_STATUS,
    REG_PIPE_TEMPERATURE,
    REG_TEMPERATURE_1,
    REG_TEMPERATURE_2,
    STATUS_COMPRESSOR_ON,
    STATUS_FAN_ON,
    STATUS_HIGH_PRESSURE_ERROR,
    STATUS_HUMIDITY_SENSOR_ERROR,
    STATUS_LOW_PRESSURE_ERROR,
    STATUS_PIPE_TEMP_ERROR,
    STATUS_ROOM_TEMP_ERROR,
    STATUS_WATER_FULL_ERROR,
)

_LOGGER = logging.getLogger(__name__)

# Create a lock for Modbus connections
MODBUS_LOCK = asyncio.Lock()


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

    # TCP
    host = config[CONF_HOST]
    port = config.get(CONF_TCP_PORT, DEFAULT_TCP_PORT)

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
    """Set up the Medole Dehumidifier sensor platform."""
    config = config_entry.data

    name = config[CONF_NAME]
    slave_id = config[CONF_SLAVE_ID]

    client = create_modbus_client(config)

    entities = [
        MedoleTemperatureSensor(name, client, slave_id, 1),
        MedoleHumiditySensor(name, client, slave_id, 1),
        MedolePipeTemperatureSensor(name, client, slave_id),
        MedoleFanOperationHoursSensor(name, client, slave_id),
        MedoleFanAlarmHoursSensor(name, client, slave_id),
        MedoleStatusSensor(name, client, slave_id),
    ]

    # Add second temperature and humidity sensors if available
    entities.extend(
        [
            MedoleTemperatureSensor(name, client, slave_id, 2),
            MedoleHumiditySensor(name, client, slave_id, 2),
        ]
    )

    async_add_entities(entities, True)


class MedoleBaseSensor(SensorEntity):
    """Base class for Medole Dehumidifier sensors."""

    _attr_has_entity_name = True

    def __init__(self, name, client, slave_id, sensor_type):
        """Initialize the sensor."""
        self._client = client
        self._slave_id = slave_id
        self._attr_unique_id = f"{name}_{sensor_type}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{name}_humidifier")},
            "name": name,
            "manufacturer": "Medole",
            "model": "IN-D17",
        }


class MedoleTemperatureSensor(MedoleBaseSensor):
    """Representation of a Medole Temperature sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, name, client, slave_id, sensor_number):
        """Initialize the temperature sensor."""
        super().__init__(name, client, slave_id, f"temperature_{sensor_number}")
        self._sensor_number = sensor_number
        self._attr_name = f"Temperature {sensor_number}"
        self._register = (
            REG_TEMPERATURE_1 if sensor_number == 1 else REG_TEMPERATURE_2
        )

    async def async_update(self) -> None:
        """Update the state of the sensor."""
        try:
            async with MODBUS_LOCK:
                if not self._client.connect():
                    _LOGGER.error("Failed to connect to Modbus device")
                    return

                result = await self.hass.async_add_executor_job(
                    lambda: self._client.read_holding_registers(
                        self._register, count=1, slave=self._slave_id
                    )
                )

            if not result.isError():
                # Temperature format: Hi Byte = decimal, Lo Byte = integer
                temp_value = result.registers[0]
                integer_part = temp_value & 0xFF
                decimal_part = (temp_value >> 8) & 0xFF
                self._attr_native_value = integer_part + decimal_part / 10
            else:
                self._attr_native_value = None

        except ModbusException as ex:
            _LOGGER.error("Error reading temperature: %s", ex)
            self._attr_native_value = None
        finally:
            self._client.close()


class MedoleHumiditySensor(MedoleBaseSensor):
    """Representation of a Medole Humidity sensor."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, name, client, slave_id, sensor_number):
        """Initialize the humidity sensor."""
        super().__init__(name, client, slave_id, f"humidity_{sensor_number}")
        self._sensor_number = sensor_number
        self._attr_name = f"Humidity {sensor_number}"
        self._register = (
            REG_HUMIDITY_1 if sensor_number == 1 else REG_HUMIDITY_2
        )

    async def async_update(self) -> None:
        """Update the state of the sensor."""
        try:
            async with MODBUS_LOCK:
                if not self._client.connect():
                    _LOGGER.error("Failed to connect to Modbus device")
                    return

                result = await self.hass.async_add_executor_job(
                    lambda: self._client.read_holding_registers(
                        self._register, count=1, slave=self._slave_id
                    )
                )

            if not result.isError():
                self._attr_native_value = result.registers[0]
            else:
                self._attr_native_value = None

        except ModbusException as ex:
            _LOGGER.error("Error reading humidity: %s", ex)
            self._attr_native_value = None
        finally:
            self._client.close()


class MedolePipeTemperatureSensor(MedoleBaseSensor):
    """Representation of a Medole Pipe Temperature sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, name, client, slave_id):
        """Initialize the pipe temperature sensor."""
        super().__init__(name, client, slave_id, "pipe_temperature")
        self._attr_name = "Pipe Temperature"

    async def async_update(self) -> None:
        """Update the state of the sensor."""
        try:
            # Acquire the lock to prevent concurrent connections
            async with MODBUS_LOCK:
                if not self._client.connect():
                    _LOGGER.error("Failed to connect to Modbus device")
                    return

                result = await self.hass.async_add_executor_job(
                    lambda: self._client.read_holding_registers(
                        REG_PIPE_TEMPERATURE, count=1, slave=self._slave_id
                    )
                )

            if not result.isError():
                self._attr_native_value = result.registers[0]
            else:
                self._attr_native_value = None

        except ModbusException as ex:
            _LOGGER.error("Error reading pipe temperature: %s", ex)
            self._attr_native_value = None
        finally:
            self._client.close()


class MedoleFanOperationHoursSensor(MedoleBaseSensor):
    """Representation of a Medole Fan Operation Hours sensor."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfTime.HOURS

    def __init__(self, name, client, slave_id):
        """Initialize the fan operation hours sensor."""
        super().__init__(name, client, slave_id, "fan_operation_hours")
        self._attr_name = "Fan Operation Hours"

    async def async_update(self) -> None:
        """Update the state of the sensor."""
        try:
            # Acquire the lock to prevent concurrent connections
            async with MODBUS_LOCK:
                if not self._client.connect():
                    _LOGGER.error("Failed to connect to Modbus device")
                    return

                result = await self.hass.async_add_executor_job(
                    lambda: self._client.read_holding_registers(
                        REG_FAN_OPERATION_HOURS, count=1, slave=self._slave_id
                    )
                )

            if not result.isError():
                self._attr_native_value = result.registers[0]
            else:
                self._attr_native_value = None

        except ModbusException as ex:
            _LOGGER.error("Error reading fan operation hours: %s", ex)
            self._attr_native_value = None
        finally:
            self._client.close()


class MedoleFanAlarmHoursSensor(MedoleBaseSensor):
    """Representation of a Medole Fan Alarm Hours sensor."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.HOURS

    def __init__(self, name, client, slave_id):
        """Initialize the fan alarm hours sensor."""
        super().__init__(name, client, slave_id, "fan_alarm_hours")
        self._attr_name = "Fan Alarm Hours"

    async def async_update(self) -> None:
        """Update the state of the sensor."""
        try:
            # Acquire the lock to prevent concurrent connections
            async with MODBUS_LOCK:
                if not self._client.connect():
                    _LOGGER.error("Failed to connect to Modbus device")
                    return

                result = await self.hass.async_add_executor_job(
                    lambda: self._client.read_holding_registers(
                        REG_FAN_ALARM_HOURS, count=1, slave=self._slave_id
                    )
                )

            if not result.isError():
                self._attr_native_value = result.registers[0]
            else:
                self._attr_native_value = None

        except ModbusException as ex:
            _LOGGER.error("Error reading fan alarm hours: %s", ex)
            self._attr_native_value = None
        finally:
            self._client.close()


class MedoleStatusSensor(MedoleBaseSensor):
    """Representation of a Medole Status sensor."""

    def __init__(self, name, client, slave_id):
        """Initialize the status sensor."""
        super().__init__(name, client, slave_id, "status")
        self._attr_name = "Status"
        self._status_value = None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if self._status_value is None:
            return {}

        lo_byte = self._status_value & 0xFF
        hi_byte = (self._status_value >> 8) & 0xFF

        return {
            "compressor_on": bool(lo_byte & STATUS_COMPRESSOR_ON),
            "fan_on": bool(lo_byte & STATUS_FAN_ON),
            "pipe_temp_error": bool(lo_byte & STATUS_PIPE_TEMP_ERROR),
            "humidity_sensor_error": bool(
                lo_byte & STATUS_HUMIDITY_SENSOR_ERROR
            ),
            "room_temp_error": bool(lo_byte & STATUS_ROOM_TEMP_ERROR),
            "water_full_error": bool(lo_byte & STATUS_WATER_FULL_ERROR),
            "high_pressure_error": bool(
                hi_byte & (STATUS_HIGH_PRESSURE_ERROR >> 8)
            ),
            "low_pressure_error": bool(
                hi_byte & (STATUS_LOW_PRESSURE_ERROR >> 8)
            ),
        }

    async def async_update(self) -> None:
        """Update the state of the sensor."""
        try:
            async with MODBUS_LOCK:
                if not self._client.connect():
                    _LOGGER.error("Failed to connect to Modbus device")
                    return

                result = await self.hass.async_add_executor_job(
                    lambda: self._client.read_holding_registers(
                        REG_OPERATION_STATUS, count=1, slave=self._slave_id
                    )
                )

            if not result.isError():
                self._status_value = result.registers[0]

                # Set the state based on errors
                errors = []
                lo_byte = self._status_value & 0xFF
                hi_byte = (self._status_value >> 8) & 0xFF

                if lo_byte & STATUS_PIPE_TEMP_ERROR:
                    errors.append("pipe_temp_error")
                if lo_byte & STATUS_HUMIDITY_SENSOR_ERROR:
                    errors.append("humidity_sensor_error")
                if lo_byte & STATUS_ROOM_TEMP_ERROR:
                    errors.append("room_temp_error")
                if lo_byte & STATUS_WATER_FULL_ERROR:
                    errors.append("water_full_error")
                if hi_byte & (STATUS_HIGH_PRESSURE_ERROR >> 8):
                    errors.append("high_pressure_error")
                if hi_byte & (STATUS_LOW_PRESSURE_ERROR >> 8):
                    errors.append("low_pressure_error")

                if errors:
                    self._attr_native_value = "Error: " + ", ".join(errors)
                elif lo_byte & STATUS_COMPRESSOR_ON:
                    self._attr_native_value = "Dehumidifying"
                elif lo_byte & STATUS_FAN_ON:
                    self._attr_native_value = "Fan Only"
                else:
                    self._attr_native_value = "Idle"
            else:
                self._attr_native_value = "Communication Error"
                self._status_value = None

        except ModbusException as ex:
            _LOGGER.error("Error reading operation status: %s", ex)
            self._attr_native_value = "Communication Error"
            self._status_value = None
        finally:
            self._client.close()
