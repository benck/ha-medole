#!/usr/bin/env python3
"""
Common register definitions for Medole Dehumidifier.
This module contains register addresses and constants used by both
the mock server and test client.
"""

# Define register addresses based on the Modbus specification
# Sensor data registers (0x6101 - 0x6112)
REG_TEMPERATURE_1 = 0x6101  # Temperature sensor 1
REG_HUMIDITY_1 = 0x6102     # Humidity sensor 1
REG_TEMPERATURE_2 = 0x6103  # Temperature sensor 2
REG_HUMIDITY_2 = 0x6104     # Humidity sensor 2
REG_OPERATION_STATUS = 0x6105  # Operation status
REG_PIPE_TEMPERATURE = 0x6106  # Pipe temperature
REG_FAN_OPERATION_HOURS = 0x6111  # Fan operation hours
REG_FAN_ALARM_HOURS = 0x6112  # Fan alarm hours

# Control registers (0x6201 - 0x6206)
REG_POWER = 0x6201  # Power on/off
REG_FAN_SPEED = 0x6202  # Fan speed
REG_HUMIDITY_SETPOINT = 0x6203  # Humidity setpoint
REG_DEHUMIDIFY_MODE = 0x6205  # Dehumidify mode
REG_PURIFY_MODE = 0x6206  # Purify mode

# Time function registers (0x6401 - 0x6404)
REG_CURRENT_TIME = 0x6401  # Current time (hour, minute)
REG_CURRENT_SECONDS = 0x6402  # Current seconds
REG_CURRENT_WEEKDAY = 0x6403  # Current weekday
REG_TIMER_FUNCTION = 0x6404  # Timer function

# Status bits for REG_OPERATION_STATUS
STATUS_COMPRESSOR_ON = 0x80  # bit7
STATUS_FAN_ON = 0x40  # bit6
STATUS_PIPE_TEMP_ERROR = 0x10  # bit4
STATUS_HUMIDITY_SENSOR_ERROR = 0x08  # bit3
STATUS_ROOM_TEMP_ERROR = 0x04  # bit2
STATUS_WATER_FULL_ERROR = 0x02  # bit1
STATUS_HIGH_PRESSURE_ERROR = 0x0800  # Hi Byte bit3
STATUS_LOW_PRESSURE_ERROR = 0x0400  # Hi Byte bit2

# Fan speed values
FAN_SPEED_LOW = 1
FAN_SPEED_MEDIUM = 2
FAN_SPEED_HIGH = 3

# Continuous dehumidification
CONTINUOUS_DEHUMIDIFICATION = 0

# Min/Max humidity setpoint
MIN_HUMIDITY = 20
MAX_HUMIDITY = 90

# Helper functions for encoding/decoding register values
def encode_temperature(integer_part, decimal_part):
    """Encode temperature value for register."""
    return (decimal_part << 8) | integer_part

def decode_temperature(value):
    """Decode temperature value from register."""
    integer_part = value & 0xFF
    decimal_part = (value >> 8) & 0xFF
    return integer_part + decimal_part / 10.0

def encode_time(hour, minute):
    """Encode time value for register."""
    return (minute << 8) | hour

def decode_time(value):
    """Decode time value from register."""
    hour = value & 0xFF
    minute = (value >> 8) & 0xFF
    return f"{hour:02d}:{minute:02d}"

def decode_operation_status(value):
    """Decode operation status from register."""
    status = {}
    status["compressor_on"] = bool(value & STATUS_COMPRESSOR_ON)
    status["fan_on"] = bool(value & STATUS_FAN_ON)
    status["pipe_temp_error"] = bool(value & STATUS_PIPE_TEMP_ERROR)
    status["humidity_sensor_error"] = bool(value & STATUS_HUMIDITY_SENSOR_ERROR)
    status["room_temp_error"] = bool(value & STATUS_ROOM_TEMP_ERROR)
    status["water_full_error"] = bool(value & STATUS_WATER_FULL_ERROR)
    status["high_pressure_error"] = bool(value & (STATUS_HIGH_PRESSURE_ERROR >> 8))
    status["low_pressure_error"] = bool(value & (STATUS_LOW_PRESSURE_ERROR >> 8))
    return status
