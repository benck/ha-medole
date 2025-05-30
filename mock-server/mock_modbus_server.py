#!/usr/bin/env python3
"""
Mock Modbus TCP Server for Medole Dehumidifier.
This script simulates a Medole Dehumidifier for testing purposes.
"""
import logging
import random
import time
from datetime import datetime
from threading import Thread

# Import register definitions from common module
from medole_registers import (
    # Other constants
    CONTINUOUS_DEHUMIDIFICATION,
    FAN_SPEED_LOW,
    MAX_HUMIDITY,
    MIN_HUMIDITY,
    REG_CURRENT_SECONDS,
    REG_CURRENT_TIME,
    REG_CURRENT_WEEKDAY,
    REG_DEHUMIDIFY_MODE,
    REG_FAN_ALARM_HOURS,
    REG_FAN_OPERATION_HOURS,
    REG_FAN_SPEED,
    REG_HUMIDITY_1,
    REG_HUMIDITY_2,
    REG_HUMIDITY_SETPOINT,
    REG_OPERATION_STATUS,
    REG_PIPE_TEMPERATURE,
    REG_POWER,
    REG_PURIFY_MODE,
    # Register addresses
    REG_TEMPERATURE_1,
    REG_TEMPERATURE_2,
    REG_TIMER_FUNCTION,
    # Status bits
    STATUS_COMPRESSOR_ON,
    STATUS_FAN_ON,
)
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.server import StartAsyncTcpServer

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
_LOGGER = logging.getLogger(__name__)


class MedoleDehumidifierMockServer:
    """Mock Modbus server for Medole Dehumidifier."""

    def __init__(self, host="localhost", port=5020):
        """Initialize the mock server."""
        self.host = host
        self.port = port
        self.server = None
        self.server_thread = None
        self.running = False

        # Initialize the data store with default values
        self.initialize_datastore()

    def initialize_datastore(self):
        """Initialize the Modbus data store with default values."""
        # Create a data block for each register range
        # We'll use a single block for all registers to simplify
        # Adjust the address offset to match the register addresses

        # Create a data block with zeros
        block = ModbusSequentialDataBlock(0, [0] * 0x7000)
        # Create the slave context
        self.context = ModbusSlaveContext(hr=block)
        # Create the server context with slave ID 1
        self.server_context = ModbusServerContext(slaves={1: self.context}, single=False)

    def set_initial_values(self):
        # Set initial values for registers
        # Temperature 1: 25.5°C (25 in low byte, 5 in high byte)
        self.context.setValues(3, REG_TEMPERATURE_1, [0x0519])
        # Humidity 1: 60%
        self.context.setValues(3, REG_HUMIDITY_1, [60])
        # Temperature 2: 26.0°C
        self.context.setValues(3, REG_TEMPERATURE_2, [0x001A])
        # Humidity 2: 60%
        self.context.setValues(3, REG_HUMIDITY_2, [60])
        # Operation status: Fan on
        self.context.setValues(3, REG_OPERATION_STATUS, [STATUS_FAN_ON])
        # Pipe temperature: 15.0°C
        self.context.setValues(3, REG_PIPE_TEMPERATURE, [0x000F])
        # Fan operation hours: 100
        self.context.setValues(3, REG_FAN_OPERATION_HOURS, [100])
        # Fan alarm hours: 2400 (default)
        self.context.setValues(3, REG_FAN_ALARM_HOURS, [2400])

        # Control registers
        # Power: Off
        self.context.setValues(3, REG_POWER, [0])
        # Fan speed: Low
        self.context.setValues(3, REG_FAN_SPEED, [FAN_SPEED_LOW])
        # Humidity setpoint: 50%
        self.context.setValues(3, REG_HUMIDITY_SETPOINT, [50])
        # Dehumidify mode: Off
        self.context.setValues(3, REG_DEHUMIDIFY_MODE, [0])
        # Purify mode: Off
        self.context.setValues(3, REG_PURIFY_MODE, [0])

        # Time function registers
        now = datetime.now()
        # Current time: hour and minute
        time_value = (now.minute << 8) | now.hour
        self.context.setValues(3, REG_CURRENT_TIME, [time_value])
        # Current seconds
        self.context.setValues(3, REG_CURRENT_SECONDS, [now.second])
        # Current weekday (1=Sunday, ..., 7=Saturday)
        weekday = now.weekday() + 2  # Convert from 0-6 (Mon-Sun) to 2-7,1 (Mon-Sat,Sun)
        if weekday == 8:
            weekday = 1
        self.context.setValues(3, REG_CURRENT_WEEKDAY, [weekday])
        # Timer function: Off
        self.context.setValues(3, REG_TIMER_FUNCTION, [0])

    def update_sensor_values(self):
        """Update sensor values periodically to simulate real device behavior."""

        self.set_initial_values()

        while self.running:
            # Get current values
            power = self.context.getValues(3, REG_POWER, 1)[0]
            dehumidify_mode = self.context.getValues(3, REG_DEHUMIDIFY_MODE, 1)[0]
            humidity_setpoint = self.context.getValues(3, REG_HUMIDITY_SETPOINT, 1)[0]

            # Get current temperature and humidity
            temp_reg = self.context.getValues(3, REG_TEMPERATURE_1, 1)[0]
            temp_int = temp_reg & 0xFF
            temp_dec = (temp_reg >> 8) & 0xFF
            current_temp = temp_int + temp_dec / 10.0

            current_humidity = self.context.getValues(3, REG_HUMIDITY_1, 1)[0]

            # Update operation status based on power and dehumidify mode
            status = 0
            if power == 1 and dehumidify_mode == 1:
                # If power is on and dehumidify mode is on
                # Check if we need to run the compressor based on humidity setpoint
                if humidity_setpoint == CONTINUOUS_DEHUMIDIFICATION or current_humidity > humidity_setpoint:
                    # Turn on compressor and fan
                    status |= STATUS_COMPRESSOR_ON | STATUS_FAN_ON
                else:
                    # Only fan is on
                    status |= STATUS_FAN_ON
            elif power == 1:
                # If power is on but dehumidify mode is off, only fan is on
                status |= STATUS_FAN_ON

            # Update operation status
            self.context.setValues(3, REG_OPERATION_STATUS, [status])

            # If compressor is running, decrease humidity slightly
            if status & STATUS_COMPRESSOR_ON:
                # Decrease humidity by 0-1% each update
                new_humidity = max(MIN_HUMIDITY, current_humidity - random.uniform(0, 1))
                self.context.setValues(3, REG_HUMIDITY_1, [int(new_humidity)])

                # Also update humidity sensor 2
                humidity2 = self.context.getValues(3, REG_HUMIDITY_2, 1)[0]
                new_humidity2 = max(MIN_HUMIDITY, humidity2 - random.uniform(0, 1))
                self.context.setValues(3, REG_HUMIDITY_2, [int(new_humidity2)])
            else:
                # Increase humidity slightly if not dehumidifying
                new_humidity = min(MAX_HUMIDITY, current_humidity + random.uniform(0, 0.5))
                self.context.setValues(3, REG_HUMIDITY_1, [int(new_humidity)])

                # Also update humidity sensor 2
                humidity2 = self.context.getValues(3, REG_HUMIDITY_2, 1)[0]
                new_humidity2 = min(MAX_HUMIDITY, humidity2 + random.uniform(0, 0.5))
                self.context.setValues(3, REG_HUMIDITY_2, [int(new_humidity2)])

            # Randomly vary temperature slightly
            new_temp = current_temp + random.uniform(-0.2, 0.2)
            new_temp_int = int(new_temp)
            new_temp_dec = int((new_temp - new_temp_int) * 10)
            new_temp_reg = (new_temp_dec << 8) | new_temp_int
            self.context.setValues(3, REG_TEMPERATURE_1, [new_temp_reg])

            # Also update temperature sensor 2
            temp2_reg = self.context.getValues(3, REG_TEMPERATURE_2, 1)[0]
            temp2_int = temp2_reg & 0xFF
            temp2_dec = (temp2_reg >> 8) & 0xFF
            current_temp2 = temp2_int + temp2_dec / 10.0
            new_temp2 = current_temp2 + random.uniform(-0.2, 0.2)
            new_temp2_int = int(new_temp2)
            new_temp2_dec = int((new_temp2 - new_temp2_int) * 10)
            new_temp2_reg = (new_temp2_dec << 8) | new_temp2_int
            self.context.setValues(3, REG_TEMPERATURE_2, [new_temp2_reg])

            # Update current time
            now = datetime.now()
            time_value = (now.minute << 8) | now.hour
            self.context.setValues(3, REG_CURRENT_TIME, [time_value])
            self.context.setValues(3, REG_CURRENT_SECONDS, [now.second])

            # Increment fan operation hours if fan is on
            if status & STATUS_FAN_ON:
                fan_hours = self.context.getValues(3, REG_FAN_OPERATION_HOURS, 1)[0]
                # In real life this would increment every hour, but for testing
                # we'll increment it slightly each update
                fan_hours += 0.01  # This will add 1 hour after 100 updates
                self.context.setValues(3, REG_FAN_OPERATION_HOURS, [int(fan_hours)])

            # Sleep for a while before the next update
            time.sleep(5)

    async def start(self):
        """Start the mock Modbus server asynchronously."""
        if self.running:
            _LOGGER.warning("Server is already running")
            return

        self.running = True

        # Start the sensor update thread
        self.update_thread = Thread(target=self.update_sensor_values)
        self.update_thread.daemon = True
        self.update_thread.start()

        # Start the Modbus server
        _LOGGER.info(f"Starting mock Modbus server on {self.host}:{self.port}")
        self.server = await StartAsyncTcpServer(
            context=self.server_context,
            address=(self.host, self.port)
        )

        _LOGGER.info(f"Mock Modbus server started on {self.host}:{self.port}")
        _LOGGER.info("Press Ctrl+C to stop the server")

    def stop(self):
        """Stop the mock Modbus server."""
        if not self.running:
            _LOGGER.warning("Server is not running")
            return

        self.running = False
        if self.server:
            self.server.server_close()
            _LOGGER.info("Mock Modbus server stopped")


if __name__ == "__main__":
    import asyncio

    # Create the mock server
    server = MedoleDehumidifierMockServer()

    # Define the main async function
    async def main():
        try:
            # Start the server
            await server.start()

            # Keep the server running until interrupted
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            _LOGGER.info("Server stopped by user")
        except Exception as e:
            _LOGGER.error(f"Error: {e}")
        finally:
            server.stop()

    # Run the async main function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # This catches Ctrl+C in the main thread
        pass
