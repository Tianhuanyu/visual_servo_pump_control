""" # MQTT Service Module

## Overview
The `mqtt_service` module provides a high-level interface for managing MQTT (Message Queuing Telemetry Transport) communications. It includes classes for managing an MQTT broker, client connections, and a service that combines both.

## Classes

### MQTTBroker
Manages the MQTT broker process.

#### Methods
- `__init__(self, host="localhost", port=1883)`: Initialize the broker with host and port.
- `start(self)`: Start the MQTT broker process.
- `stop(self)`: Stop the MQTT broker process.

### MQTTClient
Handles MQTT client operations including connecting, publishing, and subscribing.

#### Methods
- `__init__(self, broker_host, broker_port)`: Initialize the client with broker details.
- `connect(self)`: Connect to the MQTT broker.
- `disconnect(self)`: Disconnect from the MQTT broker.
- `publish(self, topic, message)`: Publish a message to a specific topic.
- `subscribe(self, topic, callback)`: Subscribe to a topic with a callback function.

### MQTTService
Combines broker and client management for a complete MQTT service.

#### Methods
- `__init__(self, host="localhost", port=1883)`: Initialize the service.
- `start(self)`: Start the broker and connect the client.
- `stop(self)`: Stop the client and broker.
- `publish(self, topic, message)`: Publish a message using the client.
- `subscribe(self, topic, callback)`: Subscribe to a topic using the client.

## Usage Example

```python
import asyncio
from mqtt_service import MQTTService

async def publish_time(mqtt_service):
    while True:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mqtt_service.publish("time/current", current_time)
        await asyncio.sleep(1)

def time_callback(client, userdata, message):
    print(f"Current time: {message.payload.decode()}")

async def main():
    mqtt_service = MQTTService()
    try:
        mqtt_service.start()
        mqtt_service.subscribe("time/current", time_callback)
        asyncio.create_task(publish_time(mqtt_service))
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        mqtt_service.stop()

if __name__ == "__main__":
    asyncio.run(main())

Dependencies
paho-mqtt: For MQTT client functionality
asyncio: For asynchronous operations

Notes
Ensure that the Mosquitto broker is installed on your system.
The broker is started on localhost by default. Modify host and port in MQTTService initialization if needed.
Error handling and reconnection logic may need to be implemented for production use. `
 """

# TODO: Add error handling and reconnection logic for production use

import asyncio
import subprocess
import time
from datetime import datetime
from paho.mqtt import client as mqtt_client

class MQTTBroker:
    def __init__(self, host="localhost", port=1883):
        self.host = host
        self.port = port
        self.process = None

    def start(self):
        try:
            self.process = subprocess.Popen(
                ["mosquitto", "-p", str(self.port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            time.sleep(1)  # Give the broker a moment to start
            if self.process.poll() is None:
                print(f"Mosquitto broker started on {self.host}:{self.port}")
            else:
                raise RuntimeError("Broker failed to start")
        except Exception as e:
            print(f"Error starting Mosquitto broker: {e}")
            raise

    def stop(self):
        if self.process:
            self.process.terminate()
            self.process.wait()
            print("Mosquitto broker stopped")

class MQTTClient:
    def __init__(self, broker_host, broker_port):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client = mqtt_client.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def connect(self):
        self.client.connect(self.broker_host, self.broker_port)
        self.client.loop_start()

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker!")
        else:
            print(f"Failed to connect, return code {rc}")

    def on_message(self, client, userdata, msg):
        print(f"Received message on topic {msg.topic}: {msg.payload.decode()}")

    def publish(self, topic, message):
        self.client.publish(topic, message)
        print(f"Published to {topic}: {message}")

    def subscribe(self, topic, callback):
        self.client.subscribe(topic)
        self.client.message_callback_add(topic, callback)

class MQTTService:
    def __init__(self, host="localhost", port=1883):
        self.host = host
        self.port = port
        self.client = None

    def start(self):
        #self.broker = MQTTBroker(self.host, self.port)
        #self.broker.start()
        self.client = MQTTClient(self.host, self.port)
        self.client.connect()
        print("MQTT Service started")

    def stop(self):
        if self.client:
            self.client.disconnect()
        print("MQTT Service stopped")

    def publish(self, topic, message):
        if self.client:
            self.client.publish(topic, message)

    def subscribe(self, topic, callback):
        if self.client:
            self.client.subscribe(topic, callback)

async def publish_time(mqtt_service):
    while True:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mqtt_service.publish("time/current", current_time)
        await asyncio.sleep(1)

def time_callback(client, userdata, message):
    print(f"Current time: {message.payload.decode()}")

async def main():
    mqtt_service = MQTTService()
    try:
        mqtt_service.start()
        mqtt_service.subscribe("time/current", time_callback)
        print("MQTT Service started. Press Ctrl+C to stop.")
        asyncio.create_task(publish_time(mqtt_service))
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Stopping MQTT Service...")
        mqtt_service.stop()
        print("MQTT Service stopped.")

if __name__ == "__main__":
    asyncio.run(main())

