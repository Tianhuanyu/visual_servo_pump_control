import json
import time
import threading
import logging
import sys
import os

# Add the parent directory to the path to make imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mqtt_service import MQTTService
from modbus_connection import ModbusConnection

logger = logging.getLogger(__name__)

class StepperMQTTController:
    """
    Combined controller that handles both MQTT communication and stepper control via Modbus.
    Eliminates the need for separate bridge and stepper device classes.
    
    This class:
    1. Connects to MQTT broker
    2. Subscribes to stepper command topics
    3. Translates MQTT commands to Modbus commands
    4. Polls stepper status and position
    5. Publishes status and position updates to MQTT
    """
    
    def __init__(self, mqtt_service: MQTTService, 
                 modbus_connection: ModbusConnection, slave_id=1, poll_interval=0.1):
        """
        Initialize the StepperMQTTController.
        
        Args:
            mqtt_service: MQTT service instance
            modbus_connection: Modbus connection instance
            slave_id: Modbus slave ID (device address)
            poll_interval: Interval in seconds between status polls (default: 0.1)
        """
        # MQTT setup
        self.mqtt = mqtt_service
        
        # Modbus setup
        self.modbus = modbus_connection
        self.slave_id = slave_id
        self.poll_interval = poll_interval
        
        # Threading
        self.running = False
        self.poll_thread = None
        self.lock = threading.Lock()

        # Create axis instances
        self.axis0 = self.Axis(self, 0)
        self.axis1 = self.Axis(self, 1)
        
        # State tracking
        self.positions = {"axis_0": 0, "axis_1": 0}
        self.status = {
            "slave_id": slave_id,
            "connected": False,
            "error": None
        }
        
        # Register command handlers
        self.command_handlers = {
            "move/absolute": self._move_absolute,
            "move/relative": self._move_relative,
            "home": self._home_axis,
            "stop": self._stop_axis,
            "enable": self._enable_axis,
            "disable": self._disable_axis,
            "reset": self._reset_axis
        }
        
        # Debug flags
        self.debug_mqtt = False
        self.debug_modbus = False


    
    
    def start(self):
        """Start the controller, connecting to MQTT and Modbus"""
        logger.info(f"Starting StepperMQTTController with slave_id={self.slave_id}")
        
        # Connect to services
        self.mqtt.start()
        connected = self.modbus.connect()
        self.status["connected"] = connected
        
        if not connected:
            logger.error(f"Failed to connect to Modbus device on port {self.modbus.port}")
            return False
        
        logger.info(f"Connected to Modbus device on port {self.modbus.port}")
        
        # Subscribe to command topics
        self._subscribe_to_commands()
        
        # Start status polling
        self.running = True
        self.poll_thread = threading.Thread(target=self._poll_status)
        self.poll_thread.daemon = True
        self.poll_thread.start()
        
        logger.info("StepperMQTTController started successfully")
        return True
    
    def stop(self):
        """Stop the controller and clean up resources"""
        logger.info("Stopping StepperMQTTController")
        self.running = False
        if self.poll_thread:
            self.poll_thread.join(timeout=1.0)
        self.modbus.disconnect()
        self.mqtt.stop()
        logger.info("StepperMQTTController stopped")
    
    def set_debug(self, mqtt_debug=None, modbus_debug=None):
        """Set debug flags for MQTT and Modbus components"""
        if mqtt_debug is not None:
            self.debug_mqtt = mqtt_debug
        if modbus_debug is not None:
            self.debug_modbus = modbus_debug
    
    def _subscribe_to_commands(self):
        """Subscribe to MQTT command topics"""
        # Subscribe to move commands
        self.mqtt.subscribe(f"stepper/+/axis/+/move/absolute", self._on_command)
        self.mqtt.subscribe(f"stepper/+/axis/+/move/relative", self._on_command)
        logger.info(f"Subscribing to topic: stepper/+/axis/+/move/absolute")
        logger.info(f"Subscribing to topic: stepper/+/axis/+/move/relative")
        
        # Subscribe to other axis commands
        self.mqtt.subscribe(f"stepper/+/axis/+/home", self._on_command)
        self.mqtt.subscribe(f"stepper/+/axis/+/stop", self._on_command)
        self.mqtt.subscribe(f"stepper/+/axis/+/enable", self._on_command)
        self.mqtt.subscribe(f"stepper/+/axis/+/disable", self._on_command)
        self.mqtt.subscribe(f"stepper/+/axis/+/reset", self._on_command)
        logger.info(f"Subscribing to topic: stepper/+/axis/+/home")
        logger.info(f"Subscribing to topic: stepper/+/axis/+/stop")
        logger.info(f"Subscribing to topic: stepper/+/axis/+/enable")
        logger.info(f"Subscribing to topic: stepper/+/axis/+/disable")
        logger.info(f"Subscribing to topic: stepper/+/axis/+/reset")
        
        # Subscribe to servo mode commands
        self.mqtt.subscribe(f"stepper/+/axis/+/enable_servo", self._on_command)
        self.mqtt.subscribe(f"stepper/+/axis/+/disable_servo", self._on_command)
        self.mqtt.subscribe(f"stepper/+/axis/+/servo_speed", self._on_command)
        logger.info(f"Subscribing to topic: stepper/+/axis/+/enable_servo")
        logger.info(f"Subscribing to topic: stepper/+/axis/+/disable_servo")
        logger.info(f"Subscribing to topic: stepper/+/axis/+/servo_speed")
        
        # Subscribe to device-level commands
        self.mqtt.subscribe(f"stepper/+/enable", self._on_command)
        self.mqtt.subscribe(f"stepper/+/disable", self._on_command)
        self.mqtt.subscribe(f"stepper/+/reset", self._on_command)
        logger.info(f"Subscribing to topic: stepper/+/enable")
        logger.info(f"Subscribing to topic: stepper/+/disable")
        logger.info(f"Subscribing to topic: stepper/+/reset")
    
    def _on_command(self, client, userdata, msg):
        """Handle incoming MQTT command messages"""
        try:
            topic = msg.topic
            payload_str = msg.payload.decode('utf-8')
            
            # Always log received commands
            logger.info(f"Received MQTT command on topic {topic}: {payload_str}")
            
            # Log debug message if debug_mqtt is enabled
            if self.debug_mqtt:
                logger.debug(f"Processing MQTT command: {topic} - {payload_str}")
            
            # Parse the topic to extract command information
            # Expected format: stepper/{stepper_id}/axis/{axis_id}/{command}
            # or: stepper/{stepper_id}/{command} for device-level commands
            topic_parts = topic.split('/')
            
            if len(topic_parts) < 3:
                logger.warning(f"Invalid topic format: {topic}")
                return
                
            # Extract stepper ID from topic
            stepper_id_str = topic_parts[1].replace('stepper', '')
            try:
                stepper_id = int(stepper_id_str)
            except ValueError:
                stepper_id = 0  # Default to 0 if not a number
                
            # Check if this command is for us
            if stepper_id != self.slave_id and stepper_id != '+':
                if self.debug_mqtt:
                    logger.debug(f"Ignoring command for different stepper: {stepper_id}")
                return
                
            # Parse the payload as JSON
            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in payload: {payload_str}")
                return
                
            # Process device-level commands
            if len(topic_parts) == 3:
                command = topic_parts[2]
                if self.debug_mqtt:
                    logger.debug(f"Processing device command: {command}")
                    
                if command == 'enable':
                    self._enable_axis(0)
                    self._enable_axis(1)
                elif command == 'disable':
                    self._disable_axis(0)
                    self._disable_axis(1)
                elif command == 'reset':
                    self._reset_axis(0)
                    self._reset_axis(1)
                else:
                    logger.warning(f"Unknown device command: {command}")
                return
                
            # Process axis-specific commands
            if len(topic_parts) >= 5 and topic_parts[2] == 'axis':
                try:
                    axis_id = int(topic_parts[3])
                except ValueError:
                    logger.error(f"Invalid axis ID: {topic_parts[3]}")
                    return
                    
                command = topic_parts[4]
                
                # For move commands, there's an additional part
                if len(topic_parts) >= 6 and topic_parts[4] == 'move':
                    command = f"move_{topic_parts[5]}"
                
                if self.debug_mqtt:
                    logger.debug(f"Processing axis command: {command} for axis {axis_id}")
                
                # Execute the appropriate command
                if command == 'move_absolute':
                    self._move_absolute(axis_id, payload)
                elif command == 'move_relative':
                    self._move_relative(axis_id, payload)
                elif command == 'home':
                    self._home_axis(axis_id, payload)
                elif command == 'stop':
                    self._stop_axis(axis_id)
                elif command == 'enable':
                    self._enable_axis(axis_id)
                elif command == 'disable':
                    self._disable_axis(axis_id)
                elif command == 'reset':
                    self._reset_axis(axis_id)
                elif command == 'enable_servo':
                    self._enable_servo_mode(axis_id, payload)
                elif command == 'disable_servo':
                    self._disable_servo_mode(axis_id)
                elif command == 'servo_speed':
                    self._set_servo_speed(axis_id, payload)
                else:
                    logger.warning(f"Unknown axis command: {command}")
                    
        except Exception as e:
            logger.exception(f"Error processing MQTT command: {e}")
    
    # ===== Command Delegation Methods =====
    
    def _move_absolute(self, axis_id, params):
        """Delegate absolute move command to the appropriate axis"""
        if axis_id == 0:
            return self.axis0._move_absolute(params)
        elif axis_id == 1:
            return self.axis1._move_absolute(params)
        else:
            logger.error(f"Invalid axis ID for move_absolute: {axis_id}")
            return False
    
    def _move_relative(self, axis_id, params):
        """Delegate relative move command to the appropriate axis"""
        if axis_id == 0:
            return self.axis0._move_relative(params)
        elif axis_id == 1:
            return self.axis1._move_relative(params)
        else:
            logger.error(f"Invalid axis ID for move_relative: {axis_id}")
            return False
    
    def _home_axis(self, axis_id, params):
        """Delegate home command to the appropriate axis"""
        if axis_id == 0:
            return self.axis0._home_axis(params)
        elif axis_id == 1:
            return self.axis1._home_axis(params)
        else:
            logger.error(f"Invalid axis ID for home: {axis_id}")
            return False
    
    def _stop_axis(self, axis_id, params=None):
        """Delegate stop command to the appropriate axis"""
        if axis_id == 0:
            return self.axis0._stop_axis()
        elif axis_id == 1:
            return self.axis1._stop_axis()
        else:
            logger.error(f"Invalid axis ID for stop: {axis_id}")
            return False
    
    def _enable_axis(self, axis_id, params=None):
        """Delegate enable command to the appropriate axis"""
        if axis_id == 0:
            return self.axis0._enable_axis()
        elif axis_id == 1:
            return self.axis1._enable_axis()
        else:
            logger.error(f"Invalid axis ID for enable: {axis_id}")
            return False
    
    def _disable_axis(self, axis_id, params=None):
        """Delegate disable command to the appropriate axis"""
        if axis_id == 0:
            return self.axis0._disable_axis()
        elif axis_id == 1:
            return self.axis1._disable_axis()
        else:
            logger.error(f"Invalid axis ID for disable: {axis_id}")
            return False
    
    def _reset_axis(self, axis_id, params=None):
        """Delegate reset command to the appropriate axis"""
        if axis_id == 0:
            return self.axis0._reset_axis()
        elif axis_id == 1:
            return self.axis1._reset_axis()
        else:
            logger.error(f"Invalid axis ID for reset: {axis_id}")
            return False

    def _enable_servo_mode(self, axis_id, params=None):
        """Enable servo mode for the specified axis"""
        logger.info(f"Enabling servo mode for axis {axis_id}")
        
        # Default parameters
        if params is None:
            params = {}
            
        # Get the axis instance
        axis = self.axis0 if axis_id == 0 else self.axis1
        
        # Call the axis method
        return axis._enable_servo_mode(params)
        
    def _disable_servo_mode(self, axis_id, params=None):
        """Disable servo mode for the specified axis"""
        logger.info(f"Disabling servo mode for axis {axis_id}")
        
        # Default parameters
        if params is None:
            params = {}
            
        # Get the axis instance
        axis = self.axis0 if axis_id == 0 else self.axis1
        
        # Call the axis method
        return axis._disable_servo_mode(params)
        
    def _set_servo_speed(self, axis_id, params):
        """Set speed in servo mode for the specified axis"""
        if not params:
            logger.error(f"No parameters provided for set_servo_speed command on axis {axis_id}")
            return False
            
        logger.info(f"Setting servo speed for axis {axis_id}: {params}")
        
        # Get the axis instance
        axis = self.axis0 if axis_id == 0 else self.axis1
        
        # Call the axis method
        return axis._set_servo_speed(params)

    # ===== Status Polling =====
    
    def _poll_status(self):
        """Poll axis status and position at regular intervals"""
        logger.info("Starting status polling thread")
        poll_count = 0
        
        # Define register addresses
        STATUS_REG = 0x0D           # Status register for both axes
        AXIS0_POSITION_REG = 0x11   # Axis 0 position registers (2 words)
        AXIS1_POSITION_REG = 0x13   # Axis 1 position registers (2 words)
        
        # Status bit masks for axis 0 (lower byte)
        AXIS0_LIMIT_NEG = 0x01
        AXIS0_LIMIT_POS = 0x02
        AXIS0_BUSY = 0x04
        AXIS0_DONE = 0x08
        AXIS0_HOMED = 0x10
        AXIS0_ERROR = 0x20
        
        # Status bit masks for axis 1 (upper byte)
        AXIS1_LIMIT_NEG = 0x0100
        AXIS1_LIMIT_POS = 0x0200
        AXIS1_BUSY = 0x0400
        AXIS1_DONE = 0x0800
        AXIS1_HOMED = 0x1000
        AXIS1_ERROR = 0x2000
        
        while self.running:
            try:
                poll_count += 1
                with self.lock:
                    # Read the status register
                    status_values = self.modbus.read_registers(
                        1, STATUS_REG, self.slave_id
                    )
                    
                    if status_values and len(status_values) > 0:
                        status_word = status_values[0]
                        
                        # Extract axis 0 status (lower byte)
                        axis0_status_dict = {
                            "limit_neg": bool(status_word & AXIS0_LIMIT_NEG),
                            "limit_pos": bool(status_word & AXIS0_LIMIT_POS),
                            "is_moving": bool(status_word & AXIS0_BUSY),
                            "is_done": bool(status_word & AXIS0_DONE),
                            "is_homed": bool(status_word & AXIS0_HOMED),
                            "has_error": bool(status_word & AXIS0_ERROR),
                            "is_servo_mode": bool(status_word & 0x40)  # Bit 6 for servo mode
                        }
                        
                        # Extract axis 1 status (upper byte)
                        axis1_status_dict = {
                            "limit_neg": bool(status_word & AXIS1_LIMIT_NEG),
                            "limit_pos": bool(status_word & AXIS1_LIMIT_POS),
                            "is_moving": bool(status_word & AXIS1_BUSY),
                            "is_done": bool(status_word & AXIS1_DONE),
                            "is_homed": bool(status_word & AXIS1_HOMED),
                            "has_error": bool(status_word & AXIS1_ERROR),
                            "is_servo_mode": bool(status_word & 0x4000)  # Bit 14 for servo mode
                        }
                        
                        # Update connection status
                        self.status["connected"] = True
                        self.status["error"] = "Error detected" if (axis0_status_dict["has_error"] or axis1_status_dict["has_error"]) else None
                        
                        if self.debug_modbus and poll_count % 10 == 0:  # Log every 10th poll to avoid spam
                            logger.debug(f"Status Word: 0x{status_word:04X}, " +
                                        f"Axis0: {axis0_status_dict}, " +
                                        f"Axis1: {axis1_status_dict}")
                    else:
                        # Default values if read fails
                        axis0_status_dict = {
                            "limit_neg": False,
                            "limit_pos": False,
                            "is_moving": False,
                            "is_done": False,
                            "is_homed": False,
                            "has_error": False,
                            "is_servo_mode": False,
                            "is_stalled": False,
                            "is_enabled": False
                        }
                        
                        axis1_status_dict = {
                            "limit_neg": False,
                            "limit_pos": False,
                            "is_moving": False,
                            "is_done": False,
                            "is_homed": False,
                            "has_error": False,
                            "is_servo_mode": False,
                            "is_stalled": False,
                            "is_enabled": False
                        }
                    
                    # Read position registers for each axis
                    # Try to read both positions in one operation if they're consecutive
                    if AXIS0_POSITION_REG + 2 == AXIS1_POSITION_REG:  # Check if registers are consecutive
                        position_regs = self.modbus.read_registers(
                            AXIS0_POSITION_REG, 4, self.slave_id  # Read both axis positions (2 words each)
                        )
                        
                        if position_regs and len(position_regs) == 4:
                            # Combine low and high registers for axis 0
                            position0 = (position_regs[1] << 16) | position_regs[0]
                            self.positions["axis_0"] = position0
                            
                            # Combine low and high registers for axis 1
                            position1 = (position_regs[3] << 16) | position_regs[2]
                            self.positions["axis_1"] = position1
                            
                            if self.debug_modbus and poll_count % 10 == 0:
                                logger.debug(f"Position axis_0: {position0}, axis_1: {position1}")
                    else:
                        # Fallback to individual reads if registers aren't consecutive
                        for axis in range(2):  # Assuming 2 axes
                            position_reg = AXIS0_POSITION_REG if axis == 0 else AXIS1_POSITION_REG
                            position_regs = self.modbus.read_registers(
                                2, position_reg, self.slave_id
                            )
                            
                            if position_regs and len(position_regs) >= 2:
                                # Combine low and high registers
                                position = (position_regs[1] << 16) | position_regs[0]
                                self.positions[f"axis_{axis}"] = position
                                
                                if self.debug_modbus and poll_count % 10 == 0:
                                    logger.debug(f"Position axis_{axis}: {position}")
                    
                    # Publish axis-specific status
                    self.mqtt.publish(
                        f"stepper/stepper{self.slave_id}/axis/0/status",
                        json.dumps(axis0_status_dict)
                    )
                    
                    self.mqtt.publish(
                        f"stepper/stepper{self.slave_id}/axis/1/status",
                        json.dumps(axis1_status_dict)
                    )
                    
                    # Publish position data for each axis individually
                    self.mqtt.publish(
                        f"stepper/stepper{self.slave_id}/axis/0/position",
                        json.dumps({"position": self.positions["axis_0"]})
                    )
                    
                    self.mqtt.publish(
                        f"stepper/stepper{self.slave_id}/axis/1/position",
                        json.dumps({"position": self.positions["axis_1"]})
                    )
                    

                    
            except Exception as e:
                logger.exception(f"Error polling status: {e}")
                self.status["connected"] = False
                
                # Try to reconnect if disconnected
                if not self.modbus.is_connected():
                    logger.warning("Modbus connection lost. Attempting to reconnect...")
                    self.status["connected"] = self.modbus.connect()
                    if self.status["connected"]:
                        logger.info("Reconnected to Modbus device")
                    else:
                        logger.error("Failed to reconnect to Modbus device")
            
            # Sleep for the polling interval
            time.sleep(self.poll_interval)
        
        logger.info("Status polling thread stopped")

    class Axis:
        def __init__(self, parent, axis_id: int):
            self.parent = parent
            self.axis_id = axis_id
        
        def _move_absolute(self, params):
            """Move axis to absolute position"""
            target = params.get('position', 0)
            target_low = target & 0xFFFF
            target_high = (target >> 16) & 0xFFFF
            speed = params.get('speed', 1000)
            accel = params.get('acceleration', 1000)
            decel = params.get('deceleration', 1000)
            
            logger.info(f"Moving axis {self.axis_id} to absolute position {target} at speed {speed}")
            
            with self.parent.lock:
                # Register 0: Command register (2 = absolute move)
                # Register 1: Target position
                # Register 2: Speed
                # Register 3: Acceleration
                result = self.parent.modbus.write_registers(
                    0,  # Starting address
                    [0x0102, self.axis_id, target_low, target_high, 0, 0, speed, accel, decel],  # Values
                    self.parent.slave_id
                )
                
                if self.parent.debug_modbus:
                    logger.debug(f"Modbus write result: {result}")
                
                # Publish acknowledgment
                self.parent.mqtt.publish(
                    f"stepper/stepper{self.parent.slave_id}/axis/{self.axis_id}/ack",
                    json.dumps({
                        "command": "move_absolute",
                        "success": result,
                        "params": {
                            "target": target,
                            "speed": speed,
                            "accel": accel,
                            "decel": decel
                        }
                    })
                )
                
                return result
        
        def _move_relative(self, params):
            """Move axis by relative distance"""
            distance = params.get('distance', 0)
            speed = params.get('speed', 1000)
            accel = params.get('acceleration', 1000)
            decel = params.get('deceleration', 1000)
            
            logger.info(f"Moving axis {self.axis_id} by relative distance {distance} at speed {speed}")
            
            with self.parent.lock:
                # Register 0: Command register (3 = relative move)
                # Register 1: Distance
                # Register 2: Speed
                # Register 3: Acceleration
                result = self.parent.modbus.write_multiple_registers( 
                    0,  # Starting address
                    [3, distance, speed, accel, decel],
                    self.parent.slave_id  # Values
                )
                
                if self.parent.debug_modbus:
                    logger.debug(f"Modbus write result: {result}")
                
                # Publish acknowledgment
                self.parent.mqtt.publish(
                    f"stepper/stepper{self.parent.slave_id}/axis/{self.axis_id}/ack",
                    json.dumps({
                        "command": "move_relative",
                        "success": result,
                        "params": {
                            "distance": distance,
                            "speed": speed,
                            "accel": accel,
                            "decel": decel
                        }
                    })
                )
                
                return result
        
        def _home_axis(self,  params):
            """Home the specified axis"""
            direction = params.get('direction', 1)
            speed = params.get('speed', 500)
            
            logger.info(f"Homing axis {self.axis_id} in direction {direction} at speed {speed}")
            
            with self.parent.lock:
                # Register 0: Command register (1 = home)
                # speed and direction are saved on the device
                result = self.parent.modbus.write_register(
                    self.parent.slave_id, 
                    0,  # Starting address
                    1  # Value
                )
                
                if self.parent.debug_modbus:
                    logger.debug(f"Modbus write result: {result}")
                
                # Publish acknowledgment
                self.parent.mqtt.publish(
                    f"stepper/stepper{self.parent.slave_id}/axis/{self.axis_id}/ack",
                    json.dumps({
                        "command": "home",
                        "success": result
                    })
                )
                
                return result
        
        def _stop_axis(self):
            """Stop the specified axis"""
            logger.info(f"Stopping axis {self.axis_id}")
            
            with self.parent.lock:
                # Register 0: Command register (0 = stop)
                result = self.parent.modbus.write_register(
                    self.parent.slave_id, 
                    0,  # Address
                    0   # Value (stop command)
                )
                
                if self.parent.debug_modbus:
                    logger.debug(f"Modbus write result: {result}")
                
                # Publish acknowledgment
                self.parent.mqtt.publish(
                    f"stepper/stepper{self.parent.slave_id}/axis/{self.axis_id}/ack",
                    json.dumps({
                        "command": "stop",
                        "success": result
                    })
                )
                
                return result
        
        def _enable_axis(self):
            """Enable the specified axis"""
            logger.info(f"Enabling axis {self.axis_id}")
            
            with self.parent.lock:
                # Register 4: Control register (bit 0 = enable)
                result = self.parent.modbus.write_register(
                    self.parent.slave_id, 
                    4,  # Address
                    1   # Value (enable)
                )
                
                if self.parent.debug_modbus:
                    logger.debug(f"Modbus write result: {result}")
                
                # Publish acknowledgment
                self.parent.mqtt.publish(
                    f"stepper/stepper{self.parent.slave_id}/axis/{self.axis_id}/ack",
                    json.dumps({
                        "command": "enable",
                        "success": result
                    })
                )
                
                return result
        
        def _disable_axis(self):
            """Disable the specified axis"""
            logger.info(f"Disabling axis {self.axis_id}")
            
            with self.parent.lock:
                # Register 4: Control register (bit 0 = enable)
                result = self.parent.modbus.write_register(
                    self.parent.slave_id, 
                    4,  # Address
                    0   # Value (disable)
                )
                
                if self.parent.debug_modbus:
                    logger.debug(f"Modbus write result: {result}")
                
                # Publish acknowledgment
                self.parent.mqtt.publish(
                    f"stepper/stepper{self.parent.slave_id}/axis/{self.axis_id}/ack",
                    json.dumps({
                        "command": "disable",
                        "success": result
                    })
                )
                
                return result
        
        def _reset_axis(self):
            """Reset the specified axis"""
            logger.info(f"Resetting axis {self.axis_id}")
            
            with self.parent.lock:
                # Register 5: Reset register
                result = self.parent.modbus.write_register(
                    self.parent.slave_id, 
                    5,  # Address
                    1   # Value (reset)
                )
                
                if self.parent.debug_modbus:
                    logger.debug(f"Modbus write result: {result}")
                
                # Publish acknowledgment
                self.parent.mqtt.publish(
                    f"stepper/stepper{self.parent.slave_id}/axis/{self.axis_id}/ack",
                    json.dumps({
                        "command": "reset",
                        "success": result
                    })
                )
                
                return result

        def _enable_servo_mode(self, params):
            """Enable servo mode for this axis"""
            logger.info(f"Enabling servo mode for axis {self.axis_id}")
            
            # Extract parameters
            max_speed = params.get('max_speed', 5000)
            accel = params.get('acceleration', 1000)
            
            with self.parent.lock:
                # Register 0: Command register (0x0201 = enable servo mode)
                # Register 1: Axis ID
                # Register 2: Max speed
                # Register 3: Acceleration
                result = self.parent.modbus.write_registers(
                    0,  # Starting address
                    [0x0201, self.axis_id, max_speed, accel],  # Values
                    self.parent.slave_id
                )
                
                if self.parent.debug_modbus:
                    logger.debug(f"Modbus write result: {result}")
                
                # Publish acknowledgment
                self.parent.mqtt.publish(
                    f"stepper/stepper{self.parent.slave_id}/axis/{self.axis_id}/ack",
                    json.dumps({
                        "command": "enable_servo_mode",
                        "success": result,
                        "params": {
                            "max_speed": max_speed,
                            "acceleration": accel
                        }
                    })
                )
                
                return result
                
        def _disable_servo_mode(self, params):
            """Disable servo mode for this axis"""
            logger.info(f"Disabling servo mode for axis {self.axis_id}")
            
            with self.parent.lock:
                # Register 0: Command register (0x0202 = disable servo mode)
                # Register 1: Axis ID
                result = self.parent.modbus.write_registers(
                    0,  # Starting address
                    [0x0202, self.axis_id],  # Values
                    self.parent.slave_id
                )
                
                if self.parent.debug_modbus:
                    logger.debug(f"Modbus write result: {result}")
                
                # Publish acknowledgment
                self.parent.mqtt.publish(
                    f"stepper/stepper{self.parent.slave_id}/axis/{self.axis_id}/ack",
                    json.dumps({
                        "command": "disable_servo_mode",
                        "success": result
                    })
                )
                
                return result
                
        def _set_servo_speed(self, params):
            """Set speed in servo mode for this axis"""
            # Extract speed parameter
            speed = params.get('speed', 0)
            
            # Convert to signed integer if needed
            if isinstance(speed, int):
                # Already an integer, no conversion needed
                pass
            elif isinstance(speed, float):
                # Convert float to integer
                speed = int(speed)
            elif isinstance(speed, str):
                # Try to convert string to integer
                try:
                    speed = int(float(speed))
                except ValueError:
                    logger.error(f"Invalid speed value: {speed}")
                    return False
            
            logger.info(f"Setting servo speed for axis {self.axis_id} to {speed}")
            
            with self.parent.lock:
                # Register 0: Command register (0x0203 = set servo speed)
                # Register 1: Axis ID
                # Register 2: Speed (signed integer)
                result = self.parent.modbus.write_registers(
                    0,  # Starting address
                    [0x0203, self.axis_id, speed],  # Values
                    self.parent.slave_id
                )
                
                if self.parent.debug_modbus:
                    logger.debug(f"Modbus write result: {result}")
                
                # Publish acknowledgment
                self.parent.mqtt.publish(
                    f"stepper/stepper{self.parent.slave_id}/axis/{self.axis_id}/ack",
                    json.dumps({
                        "command": "set_servo_speed",
                        "success": result,
                        "params": {
                            "speed": speed
                        }
                    })
                )
                
                return result

# Example usage
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    # Create the MQTT service
    mqtt_service = MQTTService(host="localhost", port=1883)
    
    # Create the Modbus connection
    modbus_connection = ModbusConnection(port="/dev/ttyUSB0", baudrate=115200)
    
    # Create and start controller
    controller = StepperMQTTController(
        mqtt_service=mqtt_service,
        modbus_connection=modbus_connection,
        slave_id=1,
        poll_interval=1.0
    )
    
    try:
        if controller.start():
            logger.info("Controller started successfully")
            
            # Enable debug logging
            controller.set_debug(mqtt_debug=True, modbus_debug=False)
            
            # Keep running until interrupted
            while True:
                time.sleep(1)
                
    except KeyboardInterrupt:
        logger.info("Shutting down controller...")
    finally:
        controller.stop() 
