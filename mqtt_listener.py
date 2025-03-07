import paho.mqtt.client as mqtt

# MQTT configuration parameters
MQTT_BROKER = "localhost"   # Replace with your broker address if needed
MQTT_PORT = 1883
MQTT_TOPIC = "color/center"

def on_connect(client, userdata, flags, rc):
    print("Connected with result code", rc)
    # Subscribe to the topic once connected
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, msg):
    print(f"Received message: {msg.payload.decode()} on topic: {msg.topic}")

def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    
    # Blocking call that processes network traffic and dispatches callbacks
    client.loop_forever()

if __name__ == '__main__':
    main()