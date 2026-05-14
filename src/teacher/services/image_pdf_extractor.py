import logging
import fitz
import pytesseract
from PIL import Image
from concurrent.futures import ProcessPoolExecutor, as_completed
import os
import time
logger = logging.getLogger(__name__)

# ---------- Logging Setup ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

pdf_path = "/Users/macbook/Desktop/langchain_adk/data/BPSC Computer TRE 4.0_____ Part-1 (4 sheet) final.pdf"


def _process_pdf_page(args):
    pdf_path, page_number = args
    start_time = time.time()

    pdf = fitz.open(pdf_path)
    page = pdf[page_number]

    text = page.get_text("text").strip()

    if len(text) > 50:
        method = "TEXT"
    else:
        pix = page.get_pixmap(dpi=200)  # faster than 300
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        text = pytesseract.image_to_string(
            img,
            config="--oem 3 --psm 6"
        )
        method = "OCR"

    pdf.close()

    duration = round(time.time() - start_time, 2)

    return page_number, text, method, duration


def extract_img_pdf_text_parallel(pdf_path):
    total_start = time.time()

    pdf = fitz.open(pdf_path)
    total_pages = len(pdf)
    pdf.close()

    logger.info(f"Starting extraction for {total_pages} pages")
    
    # Limit workers to prevent system overload
    max_workers = min(os.cpu_count(), 4)  # Cap at 4 workers
    logger.info(f"Using {max_workers} CPU cores (limited from {os.cpu_count()})")

    results = [""] * total_pages

    try:
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(_process_pdf_page, (pdf_path, i))
                for i in range(total_pages)
            ]

            for future in as_completed(futures, timeout=300):  # 5 minute timeout
                try:
                    page_number, text, method, duration = future.result(timeout=60)  # 1 minute per page
                    results[page_number] = text

                    logger.info(
                        f"Page {page_number + 1} | Method: {method} | Time: {duration}s"
                    )
                except Exception as e:
                    logger.error(f"Error processing page: {e}")
                    # Continue with other pages even if one fails
                    continue

    except Exception as e:
        logger.error(f"Multiprocessing failed: {e}")
        # Fallback to sequential processing
        logger.info("Falling back to sequential processing...")
        return extract_img_pdf_text_sequential(pdf_path)

    total_time = round(time.time() - total_start, 2)
    logger.info(f"Extraction completed in {total_time} seconds")

    return "\n".join(results)


def extract_img_pdf_text_sequential(pdf_path):
    """Fallback sequential processing for when multiprocessing fails."""
    logger.info("Using sequential PDF processing")
    total_start = time.time()
    
    pdf = fitz.open(pdf_path)
    total_pages = len(pdf)
    results = []
    
    for page_num in range(total_pages):
        try:
            page_number, text, method, duration = _process_pdf_page((pdf_path, page_num))
            results.append(text)
            logger.info(f"Page {page_number + 1} | Method: {method} | Time: {duration}s")
        except Exception as e:
            logger.error(f"Error processing page {page_num + 1}: {e}")
            results.append("")  # Add empty string for failed pages
    
    pdf.close()
    
    total_time = round(time.time() - total_start, 2)
    logger.info(f"Sequential extraction completed in {total_time} seconds")
    
    return "\n".join(results)


# if __name__ == "__main__":
#     extracted_text = extract_img_pdf_text_parallel(pdf_path)

#     with open("output.txt", "w", encoding="utf-8") as f:
#         f.write(extracted_text)

#     logger.info("Text saved to output.txt")
