# frinds/time_core.py
import time

class TimeCore:
    def __init__(self):
        self.start_time = time.perf_counter()
        self.heartbeat_count = 0

    def get_now(self):
        return time.perf_counter() - self.start_time

    def wait(self, seconds, tick=0.01):
        """Orderly wait (does not busy-spin)."""
        try:
            seconds = float(seconds)
        except:
            return
        target = self.get_now() + max(0.0, seconds)
        while self.get_now() < target:
            self.heartbeat_count += 1
            time.sleep(tick)

    def get_status(self):
        return f"หัวใจเต้นไปแล้ว {self.heartbeat_count} ครั้ง"
