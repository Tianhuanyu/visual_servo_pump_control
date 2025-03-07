# video_color_detection.py
# This script reads a local video file frame by frame, uses the shared HSV algorithm to detect the center of a specified color,
# and displays the results on the screen. Additionally, it sets up a mouse callback on the "Video" window to show the HSV value
# of the pixel under the mouse cursor.

import cv2
import numpy as np
from hsv_detection import detect_color_center  # Import the common color detection function

# Global variables for storing the current frame and mouse HSV info
current_frame = None  # The current frame displayed in the "Video" window
mouse_pos = None      # The current mouse position (x, y)
mouse_hsv = None      # The HSV value at the current mouse position

def mouse_callback(event, x, y, flags, param):
    """
    Mouse callback function to capture the mouse position over the image.
    It retrieves the BGR pixel value at (x, y), converts it to HSV,
    and updates the global variable 'mouse_hsv'.
    """
    global mouse_pos, mouse_hsv, current_frame
    if event == cv2.EVENT_MOUSEMOVE:
        mouse_pos = (x, y)
        if current_frame is not None:
            # Ensure the mouse coordinates are within the image dimensions
            if y < current_frame.shape[0] and x < current_frame.shape[1]:
                # Retrieve the BGR pixel at (x, y)
                b, g, r = current_frame[y, x]
                pixel = np.uint8([[[b, g, r]]])
                # Convert the pixel to HSV
                hsv_pixel = cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)
                h, s, v = hsv_pixel[0][0]
                mouse_hsv = (h, s, v)
                # Print the HSV values to the console
                print(f"Mouse at ({x}, {y}) - HSV: {mouse_hsv}")

def main():
    global current_frame
    # Path to the local video file (change the path as needed)
    video_path = "test_pump2.mp4"
    
    # Create a VideoCapture object to read from the video file
    cap = cv2.VideoCapture(video_path)
    
    # Define the HSV color range (example values, adjust according to target color)
    lower_hsv = np.array([140, 90, 120])  # e.g., lower bound for red color
    upper_hsv = np.array([159, 150, 186])    # e.g., upper bound for red color
    
    if not cap.isOpened():
        print("Error: Could not open video file.")
        return
    
    # Create a window and set the mouse callback for it
    cv2.namedWindow("Video")
    cv2.setMouseCallback("Video", mouse_callback)
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break  # Exit loop when video ends
        
        # Update the global current_frame for the mouse callback (make a copy to avoid unintended modifications)
        current_frame = frame.copy()
        
        # Detect the color center using the shared HSV detection function
        center, mask = detect_color_center(frame, lower_hsv, upper_hsv)
        
        if center:
            # Draw a circle at the detected center on the frame
            cv2.circle(frame, center, 5, (0, 255, 0), -1)
        
        # If mouse HSV info is available, overlay the HSV value on the frame
        if mouse_hsv is not None:
            text = f"HSV: {mouse_hsv}"
            cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                        0.8, (255, 255, 255), 2, cv2.LINE_AA)
        
        # Display the original frame and the mask
        cv2.imshow("Video", frame)
        cv2.imshow("Mask", mask)
        
        # Exit loop if 'q' key is pressed
        if cv2.waitKey(30) & 0xFF == ord('q'):
            break
    
    # Release resources and close windows
    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
