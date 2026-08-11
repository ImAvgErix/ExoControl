"""v1.1 self-check"""
from aether import __version__
from aether.synthetic import SyntheticBackend, QueueHub, CursorManager
from aether.synthetic.queue import CursorQueue
import time

print("version", __version__)
hub = QueueHub()
q1 = hub.get("a")
q2 = hub.get("b")

def work(n):
    time.sleep(0.05)
    return n * 2

r1 = q1.submit(work, 3)
r2 = q2.submit(work, 5)
assert r1 == 6 and r2 == 10
print("parallel queues ok", hub.stats())
syn = SyntheticBackend()
print("platform", syn._platform, "available", syn.available())
syn.create_cursor("w1")
print("cursors", syn.list_cursors())
print("SELF_TEST_OK")
