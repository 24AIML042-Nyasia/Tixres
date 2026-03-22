import os
import time
import tempfile
from logger import logging

def clean_temp(days_old=3, dry_run=False):
    temp_dir = tempfile.gettempdir()
    now = time.time()
    cutoff = now - (days_old * 86400)

    logging.info(f"Starting cleanup in {temp_dir}")

    for root, dirs, files in os.walk(temp_dir):
        for name in files:
            path = os.path.join(root, name)

            try:
                if os.path.getmtime(path) < cutoff:
                    if dry_run:
                        logging.info(f"[DRY RUN] Would delete: {path}")
                    else:
                        os.remove(path)
                        logging.info(f"Deleted: {path}")
            except Exception as e:
                logging.error(f"Failed: {path} | {e}")

    logging.info("Cleanup complete.")

if __name__ == "__main__":
    clean_temp(days_old=3, dry_run=False)