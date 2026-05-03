import cv2
import numpy as np
import pytesseract
from pdf2image import convert_from_bytes, pdfinfo_from_bytes

def preprocess_image(image):
    """
    Use OpenCV to preprocess the image for better OCR accuracy.
    """
    # Convert PIL Image to OpenCV format (numpy array)
    open_cv_image = np.array(image) 
    
    # Convert RGB to BGR if it's a color image
    if len(open_cv_image.shape) == 3 and open_cv_image.shape[2] == 3:
        open_cv_image = open_cv_image[:, :, ::-1].copy() 

    # Convert to grayscale
    gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)
    
    # Apply Gaussian blur to reduce noise
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Apply Otsu's thresholding to binarize the image and enhance contrast
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    return thresh

def extract_text_from_scanned_pdf(file_bytes, chunk_size=2):
    """
    Converts PDF to images iteratively in chunks to prevent memory crashes 
    on large documents, preprocesses each with OpenCV, and runs Tesseract OCR.
    """
    try:
        # Determine total pages
        info = pdfinfo_from_bytes(file_bytes)
        total_pages = info["Pages"]
        
        extracted_text = ""
        
        # Process pages iteratively (pdf2image is 1-indexed)
        for start_page in range(1, total_pages + 1, chunk_size):
            end_page = min(start_page + chunk_size - 1, total_pages)
            
            # Convert only the current chunk to images
            images = convert_from_bytes(file_bytes, first_page=start_page, last_page=end_page)
            
            for image in images:
                # Preprocess image
                processed_img = preprocess_image(image)
                
                # Extract text using Tesseract
                text = pytesseract.image_to_string(processed_img, config='--psm 3')
                extracted_text += text + "\n\n"
                
        return extracted_text.strip()
    except Exception as e:
        print(f"OCR Error: {e}")
        return ""

if __name__ == "__main__":
    print("OCR module loaded. Requires tesseract-ocr system package.")
