# hsv_detection.py
# This module provides a function to detect the center of a specified color in an image using HSV thresholding.
import cv2
import numpy as np

def detect_color_center(image, lower_hsv, upper_hsv):
    """
    Detect the centroid of the mask of the specified HSV color range after applying a morphological filter.
    
    This function first converts the input BGR image to HSV, thresholds the image to create a binary mask for the
    specified HSV range, applies a morphological opening filter to remove noise, and then computes the centroid (center of mass)
    of the resulting mask.
    
    Parameters:
        image (numpy.ndarray): Input image in BGR format.
        lower_hsv (numpy.ndarray): Lower bound for HSV thresholding.
        upper_hsv (numpy.ndarray): Upper bound for HSV thresholding.
        
    Returns:
        tuple: (center, mask)
            center: Tuple (x, y) representing the centroid of the mask, or None if the mask is empty.
            mask: The binary mask image after thresholding and morphological filtering.
    """
    import cv2
    import numpy as np

    # Convert the image from BGR to HSV color space
    hsv_img = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    
    # Create a binary mask with the given HSV range
    mask = cv2.inRange(hsv_img, lower_hsv, upper_hsv)
    
    # Apply a morphological opening filter to remove small noise
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    
    # Compute moments of the mask to get the centroid of all white pixels
    M = cv2.moments(mask)
    if M["m00"] != 0:
        cX = int(M["m10"] / M["m00"])
        cY = int(M["m01"] / M["m00"])
        return (cX, cY), mask
    else:
        # If no white pixels are found, return None for the center
        return None, mask
