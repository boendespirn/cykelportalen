"""Wrapper der kører results_agent og skriver til logfil."""
import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"

log = open("results_output.log", "w", encoding="utf-8", buffering=1)

class Tee:
    def write(self, msg):
        sys.__stdout__.write(msg)
        log.write(msg)
        log.flush()
    def flush(self):
        sys.__stdout__.flush()
        log.flush()

sys.stdout = Tee()

from dotenv import load_dotenv
load_dotenv()

from results_agent import process
process(None, None)

log.close()
