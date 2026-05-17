import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import main
from app.gallery_store import GalleryStore
from app.queue_store import QueueStore


class ProductionFeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        self.inputs = self.base / "inputs"
        self.outputs = self.base / "outputs"
        self.data = self.base / "data"
        self.temp_files = self.base / "temp"
        self.inputs.mkdir(parents=True, exist_ok=True)
        self.outputs.mkdir(parents=True, exist_ok=True)
        self.data.mkdir(parents=True, exist_ok=True)
        self.temp_files.mkdir(parents=True, exist_ok=True)

        self.prev_base = main.BASE_DIR
        self.prev_inputs = main.INPUT_DIR
        self.prev_outputs = main.OUTPUT_DIR
        self.prev_temp_dir = main.TEMP_DIR
        self.prev_gallery = main.gallery_store
        self.prev_queue = main.queue_store

        main.BASE_DIR = self.base
        main.INPUT_DIR = self.inputs
        main.OUTPUT_DIR = self.outputs
        main.TEMP_DIR = self.temp_files
        main.gallery_store = GalleryStore(self.data / "gallery.json")
        main.queue_store = QueueStore(self.data / "queue.json")

    def tearDown(self) -> None:
        main.BASE_DIR = self.prev_base
        main.INPUT_DIR = self.prev_inputs
        main.OUTPUT_DIR = self.prev_outputs
        main.TEMP_DIR = self.prev_temp_dir
        main.gallery_store = self.prev_gallery
        main.queue_store = self.prev_queue
        self.temp_dir.cleanup()

    def _run(self, coro):
        return asyncio.run(coro)

    def _create_failed_job(self, job_id: str = "job-failed") -> None:
        input_path = self.inputs / f"{job_id}.png"
        input_path.write_bytes(b"fake-input")
        job = {
            "jobId": job_id,
            "visitorName": "Guest",
            "status": "failed",
            "createdAt": "2026-05-16T00:00:00+00:00",
            "queuedAt": "2026-05-16T00:00:00+00:00",
            "retryCount": 0,
            "maxRetries": 3,
            "permanentlyFailed": False,
            "cancelRequested": False,
            "deleteRequested": False,
            "inputPath": str(input_path),
            "inputUrl": f"/inputs/{input_path.name}",
            "outputPath": str(self.outputs / f"{job_id}.png"),
            "outputUrl": f"/outputs/{job_id}.png",
            "prompt": "prompt",
            "negativePrompt": "negative",
            "preset": "default",
            "promptMode": "lively_storybook",
            "promptType": "lively_storybook",
            "generationSettings": {
                "controlWeight": 0.65,
                "denoisingStrength": 0.65,
                "controlMode": "Balanced",
                "cfgScale": 7.0,
                "steps": 30,
                "width": 768,
                "height": 768,
                "samplerName": "DPM++ 2M Karras",
            },
            "detection": {},
            "originalJobId": job_id,
            "regenerationOf": None,
            "version": 1,
            "problemTags": [],
            "estimatedSeconds": 60,
        }
        main.queue_store.create_job(job)

    def test_queue_status(self) -> None:
        self._create_failed_job("q1")
        job = main.queue_store.get_job("q1")
        job["status"] = "queued"
        main.queue_store.upsert_job(job)

        status = self._run(main.queue_status())
        self.assertIn("queueLength", status)
        self.assertEqual(status["queueLength"], 1)
        self.assertIn("jobs", status)

    def test_retry_job(self) -> None:
        self._create_failed_job("retry-job")
        payload = self._run(main.retry_job("retry-job"))
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["job"]["retryCount"], 1)

    def test_cancel_job(self) -> None:
        self._create_failed_job("cancel-job")
        job = main.queue_store.get_job("cancel-job")
        job["status"] = "queued"
        main.queue_store.upsert_job(job)
        response = self._run(main.cancel_job("cancel-job"))
        self.assertEqual(response["job"]["status"], "cancelled")

    def test_delete_job(self) -> None:
        job_id = "delete-job"
        input_path = self.inputs / f"{job_id}.png"
        output_path = self.outputs / f"{job_id}.png"
        input_path.write_bytes(b"in")
        output_path.write_bytes(b"out")
        job = {
            "jobId": job_id,
            "visitorName": "Guest",
            "status": "queued",
            "createdAt": "2026-05-16T00:00:00+00:00",
            "queuedAt": "2026-05-16T00:00:00+00:00",
            "retryCount": 0,
            "maxRetries": 3,
            "permanentlyFailed": False,
            "cancelRequested": False,
            "deleteRequested": False,
            "inputPath": str(input_path),
            "inputUrl": f"/inputs/{input_path.name}",
            "outputPath": str(output_path),
            "outputUrl": f"/outputs/{output_path.name}",
            "estimatedSeconds": 60,
        }
        main.queue_store.create_job(job)
        main.gallery_store.add_item(
            {
                "jobId": job_id,
                "visitorName": "Guest",
                "preset": "default",
                "promptMode": "lively_storybook",
                "promptType": "lively_storybook",
                "inputUrl": f"/inputs/{input_path.name}",
                "outputUrl": f"/outputs/{output_path.name}",
                "createdAt": "2026-05-16T00:00:00+00:00",
                "startedAt": "2026-05-16T00:00:01+00:00",
                "completedAt": "2026-05-16T00:00:02+00:00",
                "durationSeconds": 1.0,
                "estimatedSeconds": 60,
                "detection": {},
                "generationSettings": {},
                "prompt": "p",
                "negativePrompt": "n",
                "hidden": False,
                "hiddenAt": None,
                "updatedAt": None,
                "rating": None,
                "feedbackTags": [],
                "feedbackNote": "",
                "ratedAt": None,
            }
        )

        result = self._run(main.delete_job(job_id))
        self.assertTrue(result["deleted"])
        self.assertFalse(input_path.exists())
        self.assertFalse(output_path.exists())
        self.assertIsNone(main.queue_store.get_job(job_id))
        self.assertIsNone(main.gallery_store.get_item(job_id))

    def test_regenerate_job(self) -> None:
        source_id = "regen-source"
        source_input = self.inputs / f"{source_id}.png"
        source_input.write_bytes(b"in")
        main.queue_store.create_job(
            {
                "jobId": source_id,
                "visitorName": "Guest",
                "status": "completed",
                "createdAt": "2026-05-16T00:00:00+00:00",
                "queuedAt": "2026-05-16T00:00:00+00:00",
                "retryCount": 0,
                "maxRetries": 3,
                "permanentlyFailed": False,
                "cancelRequested": False,
                "deleteRequested": False,
                "inputPath": str(source_input),
                "inputUrl": f"/inputs/{source_input.name}",
                "outputPath": str(self.outputs / f"{source_id}.png"),
                "outputUrl": f"/outputs/{source_id}.png",
                "prompt": "base prompt",
                "negativePrompt": "base negative",
                "preset": "default",
                "promptMode": "lively_storybook",
                "promptType": "lively_storybook",
                "generationSettings": {
                    "controlWeight": 0.65,
                    "denoisingStrength": 0.65,
                    "controlMode": "Balanced",
                    "cfgScale": 7.0,
                    "steps": 30,
                    "width": 768,
                    "height": 768,
                    "samplerName": "DPM++ 2M Karras",
                },
                "detection": {},
                "originalJobId": source_id,
                "regenerationOf": None,
                "version": 1,
                "problemTags": [],
                "estimatedSeconds": 60,
            }
        )

        response = self._run(
            main.regenerate_job(
                source_id,
                main.RegenerateRequest(problemTags=["too_dark", "bad_face"]),
            )
        )
        self.assertEqual(response["status"], "queued")
        self.assertEqual(response["job"]["regenerationOf"], source_id)
        self.assertEqual(response["job"]["version"], 2)

    def test_cleanup_keep_newest(self) -> None:
        for i in range(3):
            job_id = f"cleanup-{i}"
            input_path = self.inputs / f"{job_id}.png"
            output_path = self.outputs / f"{job_id}.png"
            input_path.write_bytes(b"i")
            output_path.write_bytes(b"o")
            main.gallery_store.add_item(
                {
                    "jobId": job_id,
                    "visitorName": "Guest",
                    "preset": "default",
                    "promptMode": "lively_storybook",
                    "promptType": "lively_storybook",
                    "inputUrl": f"/inputs/{input_path.name}",
                    "outputUrl": f"/outputs/{output_path.name}",
                    "createdAt": f"2026-05-16T00:00:0{i}+00:00",
                    "startedAt": f"2026-05-16T00:00:0{i}+00:00",
                    "completedAt": f"2026-05-16T00:00:0{i}+00:00",
                    "durationSeconds": 1.0,
                    "estimatedSeconds": 60,
                    "detection": {},
                    "generationSettings": {},
                    "prompt": "p",
                    "negativePrompt": "n",
                    "hidden": False,
                    "hiddenAt": None,
                    "updatedAt": None,
                    "rating": None,
                    "feedbackTags": [],
                    "feedbackNote": "",
                    "ratedAt": None,
                }
            )

        summary = self._run(main.maintenance_cleanup(main.CleanupRequest(keepNewest=1)))
        self.assertGreaterEqual(summary["deletedJobs"], 2)

    def test_lan_relative_urls_and_reconnect(self) -> None:
        project_staff_js = Path(__file__).resolve().parents[1] / "static" / "staff.js"
        project_gallery_js = Path(__file__).resolve().parents[1] / "static" / "gallery.js"
        staff_content = project_staff_js.read_text(encoding="utf-8")
        gallery_content = project_gallery_js.read_text(encoding="utf-8")

        self.assertIn('let endpoint = "/generate";', staff_content)
        self.assertIn("fetch(endpoint, {", staff_content)
        self.assertIn('fetch("/queue/status"', staff_content)
        self.assertIn('new WebSocket(`${protocol}://${window.location.host}/ws`)', staff_content)
        self.assertNotIn("http://localhost", staff_content)
        self.assertNotIn("127.0.0.1", staff_content)
        self.assertIn('new WebSocket(`${protocol}://${window.location.host}/ws`)', gallery_content)
        self.assertIn("setTimeout(connectWebSocket, 3000)", gallery_content)


if __name__ == "__main__":
    unittest.main()
