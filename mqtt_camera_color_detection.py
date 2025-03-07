# mqtt_camera_color_detection.py
# This script captures images from the camera using Picamera2, detects the center of a specified color using the shared HSV algorithm,
# and sends the coordinate via MQTT.

import cv2
import time
import numpy as np
import paho.mqtt.client as mqtt
from picamera2 import Picamera2
from hsv_detection import detect_color_center  # Import the common color detection function

# MQTT configuration parameters
MQTT_BROKER = "localhost"  # Change to your MQTT broker address if needed
MQTT_PORT = 1883
MQTT_TOPIC = "color/center"

def send_mqtt_message(client, topic, message):
    """
    Publish a message to the specified MQTT topic.
    
    Parameters:
        client: MQTT client instance.
        topic (str): The MQTT topic to publish to.
        message (str): The message payload.
    """
    client.publish(topic, message)

def main():
    # Setup MQTT client and connect to the broker
    client = mqtt.Client()
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    
    # Setup the camera using Picamera2
    picam2 = Picamera2()
    # Create a preview configuration for the camera
    config = picam2.create_preview_configuration()
    picam2.configure(config)
    picam2.start()
    
    # Allow the camera to warm up
    time.sleep(2)
    
    # Define the HSV color range (example values, adjust according to target color)
    lower_hsv = np.array([140, 90, 120])  # e.g., lower bound for red color
    upper_hsv = np.array([159, 150, 186])    # e.g., upper bound for red color
    
    try:
        while True:
            # Capture an image from the camera
            image = picam2.capture_array()
            # Convert image from RGB (Picamera2 default) to BGR for OpenCV processing
            current_image = image.copy()
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            
            # Detect the color center using the shared function
            center, mask = detect_color_center(image, lower_hsv, upper_hsv)
            
            if center:
                print("Detected center at:", center)
                # Send the detected center via MQTT as a string
                send_mqtt_message(client, MQTT_TOPIC, str(center))
            else:
                print("No color detected")
                send_mqtt_message(client, MQTT_TOPIC, str((-1,-1)))

            cv2.imshow("Video", current_image)
            cv2.imshow("Mask", mask)
            
            # Delay before next frame capture
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting program.")
    finally:
        picam2.stop()
        client.disconnect()

if __name__ == '__main__':
    main()
