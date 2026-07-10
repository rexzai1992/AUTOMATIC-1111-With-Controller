import json
import logging
import os
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psutil
import requests

from local_ai_config import BASE_DIR, LOG_DIR, PID_STATE_PATH, load_local_ai_config


logger = logging.getLogger("local-ai-service-manager")
_lock = threading.RLock()

if not logger.handlers:
    handler = logging.FileHandler(LOG_DIR / "service_manager.log", encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _read_pid_state() -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(PID_STATE_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_pid_state(state: dict[str, dict[str, Any]]) -> None:
    PID_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = PID_STATE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temp_path.replace(PID_STATE_PATH)


def health_check(url: str, timeout_seconds: float = 3.0) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = requests.get(url, timeout=timeout_seconds)
        healthy = 200 <= response.status_code < 400
        payload: Any = None
        content_type = response.headers.get("content-type", "")
        if "json" in content_type:
            try:
                payload = response.json()
            except ValueError:
                payload = None
        if isinstance(payload, dict):
            if str(payload.get("status", "")).lower() in {
                "loading",
                "degraded",
                "error",
                "failed",
            }:
                healthy = False
            if payload.get("model_loaded") is False:
                healthy = False
        return {
            "healthy": healthy,
            "status_code": response.status_code,
            "response_time_ms": round((time.perf_counter() - started) * 1000, 1),
            "payload": payload,
        }
    except requests.RequestException as exc:
        return {
            "healthy": False,
            "error": str(exc),
            "response_time_ms": round((time.perf_counter() - started) * 1000, 1),
        }


def is_port_running(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=0.5):
            return True
    except OSError:
        return False


def wait_for_health(url: str, timeout_seconds: int = 120) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_result: dict[str, Any] = {"healthy": False, "error": "Not checked."}
    while time.monotonic() < deadline:
        last_result = health_check(url, timeout_seconds=4)
        if last_result["healthy"]:
            return last_result
        time.sleep(1)
    last_result["error"] = last_result.get("error") or (
        f"Health check timed out after {timeout_seconds} seconds."
    )
    return last_result


def _service_port(service: dict[str, Any]) -> int:
    parsed = urlparse(str(service["url"]))
    return int(parsed.port or (443 if parsed.scheme == "https" else 80))


def _verified_managed_process(
    service_name: str,
) -> tuple[psutil.Process | None, dict[str, Any] | None]:
    state = _read_pid_state()
    record = state.get(service_name)
    if not record:
        return None, None
    try:
        process = psutil.Process(int(record["pid"]))
        recorded_create_time = float(record.get("create_time", 0))
        if recorded_create_time and abs(process.create_time() - recorded_create_time) > 1:
            raise psutil.NoSuchProcess(process.pid)
        if not process.is_running():
            raise psutil.NoSuchProcess(process.pid)
        return process, record
    except (psutil.Error, KeyError, TypeError, ValueError):
        state.pop(service_name, None)
        _write_pid_state(state)
        return None, None


def get_service_status(service_name: str) -> dict[str, Any]:
    config = load_local_ai_config()
    service = config["services"].get(service_name)
    if service is None:
        return {
            "service": service_name,
            "status": "unknown",
            "error": f"Unknown service: {service_name}",
        }
    health = health_check(str(service["health_url"]))
    process, record = _verified_managed_process(service_name)
    port_busy = is_port_running(_service_port(service))
    if health["healthy"]:
        status = "running"
    elif process and port_busy:
        status = "error"
    elif process:
        status = "starting"
    elif port_busy:
        status = "port_busy"
    else:
        status = "stopped"
    return {
        "service": service_name,
        "status": status,
        "enabled": bool(service.get("enabled", True)),
        "url": service["url"],
        "health_url": service["health_url"],
        "port": _service_port(service),
        "managed": process is not None,
        "pid": process.pid if process else None,
        "started_at": record.get("started_at") if record else None,
        "health": health,
    }


def get_all_service_statuses() -> dict[str, dict[str, Any]]:
    services = load_local_ai_config()["services"]
    names = list(services)
    with ThreadPoolExecutor(max_workers=max(1, len(names))) as executor:
        statuses = executor.map(get_service_status, names)
        return dict(zip(names, statuses))


def start_service(service_name: str) -> dict[str, Any]:
    with _lock:
        config = load_local_ai_config()
        service = config["services"].get(service_name)
        if service is None:
            return {"success": False, "error": f"Unknown service: {service_name}"}
        if not service.get("enabled", True):
            return {"success": False, "error": f"{service_name} is disabled."}
        current = get_service_status(service_name)
        if current["status"] == "running":
            return {
                "success": True,
                "already_running": True,
                "status": current,
            }
        if current["status"] == "port_busy":
            return {
                "success": False,
                "error": (
                    f"Port {current['port']} is occupied but "
                    f"{service_name} health check failed."
                ),
                "status": current,
            }

        cwd = Path(str(service["directory"]))
        if not cwd.is_dir():
            return {"success": False, "error": f"Service directory not found: {cwd}"}
        command = str(service["start_command"]).strip()
        executable_token = command.split()[0].strip('"')
        if executable_token.lower().endswith(".bat") and not (cwd / executable_token).is_file():
            return {
                "success": False,
                "error": f"Start script not found: {cwd / executable_token}",
            }

        log_path = Path(str(service.get("log_file", f"logs/{service_name}.log")))
        if not log_path.is_absolute():
            log_path = BASE_DIR / log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("a", encoding="utf-8", buffering=1)
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        use_shell = executable_token.lower().endswith((".bat", ".cmd"))
        try:
            # Windows batch files require cmd.exe; shell use is limited to configured .bat/.cmd launchers.
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                shell=use_shell,
                creationflags=creationflags,
            )
        except OSError as exc:
            log_handle.close()
            logger.exception("Failed to start %s", service_name)
            return {"success": False, "error": str(exc)}
        finally:
            log_handle.close()

        ps_process = psutil.Process(process.pid)
        state = _read_pid_state()
        state[service_name] = {
            "pid": process.pid,
            "create_time": ps_process.create_time(),
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "command": command,
            "cwd": str(cwd),
        }
        _write_pid_state(state)
        logger.info("Started %s pid=%s command=%s", service_name, process.pid, command)

        timeout = int(service.get("startup_timeout_seconds", 120))
        ready = wait_for_health(str(service["health_url"]), timeout)
        status = get_service_status(service_name)
        return {
            "success": bool(ready["healthy"]),
            "pid": process.pid,
            "status": status,
            "error": None if ready["healthy"] else ready.get("error"),
        }


def stop_service(service_name: str) -> dict[str, Any]:
    with _lock:
        process, _record = _verified_managed_process(service_name)
        if process is None:
            status = get_service_status(service_name)
            if status.get("status") == "running":
                return {
                    "success": False,
                    "error": (
                        f"{service_name} is running but was not started by this "
                        "manager; refusing to stop an unowned process."
                    ),
                    "status": status,
                }
            return {"success": True, "already_stopped": True, "status": status}

        pid = process.pid
        try:
            children = process.children(recursive=True)
            for child in children:
                child.terminate()
            process.terminate()
            _gone, alive = psutil.wait_procs([*children, process], timeout=10)
            for remaining in alive:
                remaining.kill()
            psutil.wait_procs(alive, timeout=5)
        except psutil.NoSuchProcess:
            pass
        except psutil.Error as exc:
            logger.exception("Failed to stop %s pid=%s", service_name, pid)
            return {"success": False, "error": str(exc)}
        state = _read_pid_state()
        state.pop(service_name, None)
        _write_pid_state(state)
        logger.info("Stopped %s pid=%s", service_name, pid)
        return {"success": True, "pid": pid, "status": get_service_status(service_name)}


def restart_service(service_name: str) -> dict[str, Any]:
    stopped = stop_service(service_name)
    if not stopped.get("success"):
        return {"success": False, "stage": "stop", **stopped}
    started = start_service(service_name)
    return {"success": bool(started.get("success")), "stop": stopped, "start": started}


def autostart_services() -> dict[str, Any]:
    results = {}
    for name, service in load_local_ai_config()["services"].items():
        if service.get("enabled", True) and service.get("autostart", False):
            results[name] = start_service(name)
    return results
