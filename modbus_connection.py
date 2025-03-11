"""
Modbus Connection Module

This module uses pymodbus to open a serial RTU connection.
Install pymodbus with:
    pip install pymodbus
"""

import logging
import serial
from pymodbus.client.serial import ModbusSerialClient as ModbusClient
from pymodbus.transaction import ModbusRtuFramer

# Debug flag to control pymodbus logging verbosity
DEBUG = True  # Set to True to enable detailed pymodbus logging

# Set default logging to INFO level instead of DEBUG
logging.basicConfig(level=logging.INFO)

class ModbusConnection:
    def __init__(self, port: str, baudrate: int = 9600):
        self.port = port
        self.baudrate = baudrate
        
        # Configure pymodbus logging based on DEBUG flag
        from pymodbus import pymodbus_apply_logging_config
        if DEBUG:
            pymodbus_apply_logging_config(logging.DEBUG)
        else:
            pymodbus_apply_logging_config(logging.WARNING)  # Only show warnings and errors
        
        # Create custom framer
        self.framer = ModbusRtuFramer(None)
        
        self.client = ModbusClient(
            method='rtu',
            port=port,
            baudrate=baudrate,
            parity='N',
            stopbits=1,
            bytesize=8
        )
        self._connected = False

    def connect(self) -> bool:
        """Connect to the Modbus device"""
        try:
            if self._connected:
                logging.info("Already connected to Modbus device")
                return True
                
            logging.info(f"Attempting to connect to port {self.port} with baudrate {self.baudrate}")
            
            # First test if we can open the port at all
            try:
                ser = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=1
                )
                ser.close()
                logging.info("Basic serial port test successful")
            except Exception as serial_e:
                logging.error(f"Failed basic serial port test: {str(serial_e)}")
                return False
            
            # Now try Modbus connection
            try:
                connect_result = self.client.connect()
                if connect_result:
                    self._connected = True
                    logging.info(f"Successfully connected to Modbus RTU bus on port {self.port}")
                    return True
                else:
                    # Get more information about why connect failed
                    logging.error(f"Failed to connect to Modbus RTU bus on port {self.port}")
                    logging.error(f"Client state - Connected: {self.client.connected}")
                    return False
            except Exception as connect_e:
                logging.error(f"Exception during Modbus connect: {str(connect_e)}")
                return False
                
        except Exception as e:
            logging.error(f"Error in connect method: {str(e)}")
            self._connected = False
            return False

    def disconnect(self) -> bool:
        """Disconnect from the Modbus device"""
        try:
            if not self._connected:
                return True
                
            self.client.close()
            self._connected = False
            logging.info("Modbus connection closed")
            return True
        except Exception as e:
            logging.error(f"Error disconnecting from Modbus device: {e}")
            return False

    def is_connected(self) -> bool:
        """Check if connected to Modbus device"""
        try:
            if not self._connected:
                return False
                
            # Simple read from slave ID 1
            result = self.client.read_holding_registers(0, 1, slave=1)

            if result and not result.isError():
                logging.info("Successfully communicated with device")
                return True
            else:
                logging.error("No response from device")
                self._connected = False
                return False
                
        except Exception as e:
            logging.error(f"Error checking connection: {str(e)}")
            self._connected = False
            return False

    def read_registers(self, address: int, count: int, slave_id: int):
        if not self._connected:
            logging.error("Not connected to Modbus device")
            return None
            
        result = self.client.read_holding_registers(address, count, slave=slave_id)
        if not result.isError():
            logging.debug(f"Slave {slave_id}: Read registers at {hex(address)}: {result.registers}")
            return result.registers
        else:
            logging.error(f"Slave {slave_id}: Error reading registers at {hex(address)}")
            return None

    def write_registers(self, address: int, values: list, slave_id: int):
        if not self._connected:
            logging.error("Not connected to Modbus device")
            return False
            
        result = self.client.write_registers(address, values, slave=slave_id)
        if not result.isError():
            logging.debug(f"Slave {slave_id}: Wrote {values} starting at {hex(address)}")
            return True
        else:
            logging.error(f"Slave {slave_id}: Error writing registers at {hex(address)}")
            return False
        
    def write_register(self, address: int, value: int, slave_id: int):
        if not self._connected:
            logging.error("Not connected to Modbus device")
            return False
            
        result = self.client.write_register(address, value, slave=slave_id)
        return result.isError()