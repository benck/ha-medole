"""Modbus client utilities for Medole Dehumidifier."""

 # ruff: noqa: I001
import asyncio
import logging
from typing import Any, Dict, List, Optional, Union

from homeassistant.core import HomeAssistant
from pymodbus.client import ModbusSerialClient
from pymodbus.client import ModbusTcpClient
from pymodbus.client import ModbusTcpClient as ModbusRtuOverTcpClient
from pymodbus.exceptions import ModbusException

from .const import (
    CONF_BAUDRATE,
    CONF_BYTESIZE,
    CONF_CONNECTION_TYPE,
    CONF_HOST,
    CONF_PARITY,
    CONF_PORT,
    CONF_STOPBITS,
    CONF_TCP_PORT,
    CONNECTION_TYPE_RTUOVERTCP,
    CONNECTION_TYPE_SERIAL,
    DEFAULT_BAUDRATE,
    DEFAULT_BYTESIZE,
    DEFAULT_PARITY,
    DEFAULT_STOPBITS,
    DEFAULT_TCP_PORT,
)

_LOGGER = logging.getLogger(__name__)

# Create a global lock for Modbus connections
MODBUS_LOCK = asyncio.Lock()


def create_modbus_client(
    config: Dict[str, Any],
) -> Union[ModbusSerialClient, ModbusTcpClient]:
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


async def async_read_register(
    hass: HomeAssistant,
    client: Union[ModbusSerialClient, ModbusTcpClient],
    address: int,
    slave_id: int,
    count: int = 1,
) -> Optional[Any]:
    """Read a register with proper connection handling and locking."""
    try:
        async with MODBUS_LOCK:
            if not client.connect():
                _LOGGER.error("Failed to connect to Modbus device")
                return None

            result = await hass.async_add_executor_job(
                lambda: client.read_holding_registers(
                    address, count=count, slave=slave_id
                )
            )

            if result.isError():
                _LOGGER.error(f"Error reading register {address}: {result}")
                return None

            return result
    except ModbusException as ex:
        _LOGGER.error(f"Modbus exception reading register {address}: {ex}")
        return None
    finally:
        client.close()


async def async_write_register(
    hass: HomeAssistant,
    client: Union[ModbusSerialClient, ModbusTcpClient],
    address: int,
    value: int,
    slave_id: int,
) -> bool:
    """Write to a register with proper connection handling and locking."""
    try:
        async with MODBUS_LOCK:
            if not client.connect():
                _LOGGER.error("Failed to connect to Modbus device")
                return False

            result = await hass.async_add_executor_job(
                lambda: client.write_register(address, value, slave=slave_id)
            )

            if result.isError():
                _LOGGER.error(f"Error writing to register {address}: {result}")
                return False

            return True
    except ModbusException as ex:
        _LOGGER.error(f"Modbus exception writing to register {address}: {ex}")
        return False
    finally:
        client.close()


async def async_write_registers(
    hass: HomeAssistant,
    client: Union[ModbusSerialClient, ModbusTcpClient],
    address: int,
    values: List[int],
    slave_id: int,
) -> bool:
    """Write multiple registers with proper connection handling and locking."""
    try:
        async with MODBUS_LOCK:
            if not client.connect():
                _LOGGER.error("Failed to connect to Modbus device")
                return False

            result = await hass.async_add_executor_job(
                lambda: client.write_registers(address, values, slave=slave_id)
            )

            if result.isError():
                _LOGGER.error(
                    f"Error writing to registers at {address}: {result}"
                )
                return False

            return True
    except ModbusException as ex:
        _LOGGER.error(
            f"Modbus exception writing to registers at {address}: {ex}"
        )
        return False
    finally:
        client.close()
