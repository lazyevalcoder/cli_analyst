import sys
import time
from pathlib import Path

sys.path.insert(0, "src")
from analyst.viewer import start_background

projects_base = Path(__file__).parent / "projects"
server = start_background(projects_base, 8081)
print("Viewer serving on http://localhost:8081", flush=True)
while True:
    time.sleep(60)
