import os
import socket
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "docker-start.sh"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run_script(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(env)
    return subprocess.run([str(SCRIPT)], cwd=str(REPO_ROOT), env=merged, text=True, capture_output=True)


def test_docker_start_tries_host_launch_then_uses_external_cdp_when_available():
    port = _free_port()
    profile_dir = tempfile.mkdtemp(prefix="clausy-profile-")
    server_code = textwrap.dedent(
        """
        import json
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/json/version':
                    body = json.dumps({'webSocketDebuggerUrl': 'ws://example'}).encode('utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()
            def log_message(self, *args, **kwargs):
                return

        HTTPServer(('127.0.0.1', %d), H).serve_forever()
        """ % port
    )
    server = subprocess.Popen([sys.executable, "-c", server_code], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        completed = _run_script(
            {
                "CLAUSY_DOCKER_START_DRY_RUN": "1",
                "CLAUSY_CDP_HOST": "127.0.0.1",
                "CLAUSY_CDP_PORT": str(port),
                "CLAUSY_PROFILE_DIR": profile_dir,
                "CLAUSY_HOST_BROWSER_LAUNCH_CMD": "true",
            }
        )
    finally:
        server.terminate()
        server.wait(timeout=5)

    assert completed.returncode == 0, completed.stderr
    combined = completed.stdout + completed.stderr
    assert "Step 1/3: attempting host-browser launch path" in combined
    assert "Step 2/3: probing configured CDP endpoint" in combined
    assert "mode=external-host" in combined
    assert "runtime mode selected: external-host-cdp" in combined


def test_docker_start_rejects_unknown_launch_placeholders_and_falls_back():
    profile_dir = tempfile.mkdtemp(prefix="clausy-profile-")
    marker = Path(profile_dir) / "should-not-exist"
    completed = _run_script(
        {
            "CLAUSY_DOCKER_START_DRY_RUN": "1",
            "CLAUSY_CDP_HOST": "127.0.0.1",
            "CLAUSY_CDP_PORT": "65534",
            "CLAUSY_PROFILE_DIR": profile_dir,
            "CLAUSY_BROWSER_BINARY": "/bin/sh",
            "CLAUSY_HOST_BROWSER_LAUNCH_CMD": f"touch {marker} {{unknown}}",
        }
    )

    assert completed.returncode == 0, completed.stderr
    combined = completed.stdout + completed.stderr
    assert "Host-browser launch command rejected" in combined
    assert "Step 3/3: trying local in-container Chromium fallback" in combined
    assert "runtime mode selected: local-chromium-fallback" in combined
    assert not marker.exists()


def test_docker_start_falls_back_to_local_after_host_launch_and_probe_fail():
    profile_dir = tempfile.mkdtemp(prefix="clausy-profile-")
    completed = _run_script(
        {
            "CLAUSY_DOCKER_START_DRY_RUN": "1",
            "CLAUSY_CDP_HOST": "127.0.0.1",
            "CLAUSY_CDP_PORT": "65534",
            "CLAUSY_PROFILE_DIR": profile_dir,
            "CLAUSY_BROWSER_BINARY": "/bin/sh",
            "CLAUSY_HOST_BROWSER_LAUNCH_CMD": "false",
        }
    )

    assert completed.returncode == 0, completed.stderr
    combined = completed.stdout + completed.stderr
    assert "Step 1/3: attempting host-browser launch path" in combined
    assert "Host-browser launch attempt did not succeed" in combined
    assert "Step 2/3: probing configured CDP endpoint" in combined
    assert "Step 3/3: trying local in-container Chromium fallback" in combined
    assert "runtime mode selected: local-chromium-fallback" in combined
    assert "--remote-debugging-address=0.0.0.0" in combined
    assert "--remote-debugging-port=65534" in combined
    assert f"--user-data-dir={profile_dir}" in combined
