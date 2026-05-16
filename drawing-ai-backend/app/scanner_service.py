import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional, Set

from watchdog.events import FileCreatedEvent, FileMovedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.config import SCANNER_ALLOWED_EXTENSIONS


logger = logging.getLogger(__name__)


class ScannerWatcherHandler(FileSystemEventHandler):
    def __init__(self, scanner_service: "ScannerService") -> None:
        super().__init__()
        self._scanner_service = scanner_service

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory:
            return
        self._scanner_service.handle_candidate(Path(event.src_path))

    def on_moved(self, event: FileMovedEvent) -> None:
        if event.is_directory:
            return
        self._scanner_service.handle_candidate(Path(event.dest_path))


class ScannerService:
    def __init__(
        self,
        scanner_input_dir: Path,
        on_file_ready: Callable[[Path, str], None],
        enabled: bool = True,
    ) -> None:
        self.scanner_input_dir = scanner_input_dir
        self._on_file_ready = on_file_ready
        self._enabled = enabled
        self._observer: Optional[Observer] = None
        self._processing_lock = threading.Lock()
        self._processing_paths: Set[str] = set()

    @property
    def running(self) -> bool:
        return bool(self._observer and self._observer.is_alive())

    def start(self) -> None:
        if not self._enabled:
            logger.info("Scanner folder watcher is disabled by configuration.")
            return

        self.scanner_input_dir.mkdir(parents=True, exist_ok=True)
        event_handler = ScannerWatcherHandler(self)
        observer = Observer()
        observer.schedule(event_handler, str(self.scanner_input_dir), recursive=False)
        observer.daemon = True
        observer.start()
        self._observer = observer
        logger.info("Scanner watcher started for folder: %s", self.scanner_input_dir)

    def stop(self) -> None:
        if not self._observer:
            return

        self._observer.stop()
        self._observer.join(timeout=5)
        logger.info("Scanner watcher stopped.")

    def handle_candidate(self, file_path: Path) -> None:
        if file_path.suffix.lower() not in SCANNER_ALLOWED_EXTENSIONS:
            return

        absolute = str(file_path.resolve())
        with self._processing_lock:
            if absolute in self._processing_paths:
                return
            self._processing_paths.add(absolute)

        threading.Thread(
            target=self._process_candidate,
            args=(file_path,),
            daemon=True,
        ).start()

    def _process_candidate(self, file_path: Path) -> None:
        absolute = str(file_path.resolve())
        try:
            ready = self._wait_until_copy_complete(file_path)
            if not ready:
                logger.warning("Scanner file did not stabilize before timeout: %s", file_path)
                return

            visitor_name = self._visitor_name_from_path(file_path)
            logger.info("Scanner file detected and ready: %s", file_path)
            self._on_file_ready(file_path, visitor_name)
        except Exception:
            logger.exception("Failed to process scanner input file: %s", file_path)
        finally:
            with self._processing_lock:
                self._processing_paths.discard(absolute)

    @staticmethod
    def _visitor_name_from_path(file_path: Path) -> str:
        cleaned = file_path.stem.replace("_", " ").replace("-", " ").strip()
        return cleaned if cleaned else "Scanner Guest"

    @staticmethod
    def _wait_until_copy_complete(
        file_path: Path,
        timeout_seconds: int = 120,
        poll_seconds: float = 0.5,
        stable_checks_required: int = 3,
    ) -> bool:
        stable_checks = 0
        last_size = -1
        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            if not file_path.exists():
                time.sleep(poll_seconds)
                continue

            try:
                current_size = file_path.stat().st_size
                if current_size > 0 and current_size == last_size:
                    stable_checks += 1
                else:
                    stable_checks = 0

                last_size = current_size

                if stable_checks >= stable_checks_required:
                    with file_path.open("rb"):
                        return True
            except OSError:
                stable_checks = 0

            time.sleep(poll_seconds)

        return False

