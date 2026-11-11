import shlex
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from harbor.auth import constants
from harbor.auth.tokens import invalidate_token
from harbor.storage.resumable import upload_resumable_file

pytestmark = pytest.mark.unit


class StubHub:
    def __init__(self):
        self.objects: dict[str, bytearray] = {}
        self.paths: list[str] = []
        self.patch_offsets: list[int] = []
        self.initial_token: str | None = None
        self.reject_first_token = False
        self.reject_next_patches = 0

        hub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def _send(self, status: int, headers: dict[str, str] | None = None):
                self.send_response(status)
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.end_headers()

            def do_POST(self):
                hub.paths.append(self.path)
                assert self.path == "/hub/storage/v1/upload/resumable"
                hub.initial_token = self.headers["Authorization"].removeprefix(
                    "Bearer "
                )
                upload_id = str(len(hub.objects) + 1)
                hub.objects[upload_id] = bytearray()
                self._send(
                    201,
                    {"Location": f"/storage/v1/upload/resumable/{upload_id}"},
                )

            def do_HEAD(self):
                hub.paths.append(self.path)
                upload_id = self.path.rsplit("/", 1)[-1]
                self._send(
                    200,
                    {"Upload-Offset": str(len(hub.objects[upload_id]))},
                )

            def do_PATCH(self):
                hub.paths.append(self.path)
                upload_id = self.path.rsplit("/", 1)[-1]
                token = self.headers["Authorization"].removeprefix("Bearer ")
                data = self.rfile.read(int(self.headers["Content-Length"]))
                if hub.reject_next_patches:
                    hub.reject_next_patches -= 1
                    self._send(401, {"Content-Length": "0"})
                    return
                if hub.reject_first_token and token == hub.initial_token:
                    hub.reject_first_token = False
                    self._send(401, {"Content-Length": "0"})
                    return
                offset = int(self.headers["Upload-Offset"])
                hub.patch_offsets.append(offset)
                if offset != len(hub.objects[upload_id]):
                    self._send(409)
                    return
                hub.objects[upload_id].extend(data)
                self._send(
                    204,
                    {"Upload-Offset": str(len(hub.objects[upload_id]))},
                )

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


def _token_command(counter: Path) -> str:
    script = (
        "import base64,json,pathlib,time; "
        f"p=pathlib.Path({str(counter)!r}); "
        "n=int(p.read_text())+1 if p.exists() else 1; p.write_text(str(n)); "
        "payload=base64.urlsafe_b64encode(json.dumps({'exp':int(time.time())+3600,'n':n}).encode()).decode().rstrip('='); "
        "print('e30.'+payload+'.sig')"
    )
    return shlex.join([sys.executable, "-c", script])


@pytest.fixture
def stub_hub(monkeypatch, tmp_path):
    hub = StubHub()
    monkeypatch.setattr(constants, "SUPABASE_URL", hub.base_url + "/hub")
    monkeypatch.setattr("harbor.storage.resumable.SUPABASE_URL", hub.base_url + "/hub")
    monkeypatch.setattr(
        constants, "ACCESS_TOKEN_COMMAND", _token_command(tmp_path / "runs")
    )
    invalidate_token()
    yield hub, tmp_path / "runs"
    invalidate_token()
    hub.close()


@pytest.mark.asyncio
async def test_large_upload_round_trips_bytes_and_prefix(stub_hub, tmp_path):
    hub, counter = stub_hub
    source = tmp_path / "large.bin"
    payload = bytes(range(256)) * (13 * 1024 * 1024 // 256)
    source.write_bytes(payload)

    assert await upload_resumable_file(source, "object.bin", bucket="results")

    assert bytes(hub.objects["1"]) == payload
    assert hub.paths[0] == "/hub/storage/v1/upload/resumable"
    assert all(path.startswith("/hub/") for path in hub.paths[1:])
    assert counter.read_text() == "1"


@pytest.mark.asyncio
async def test_patch_401_refreshes_command_token_once(stub_hub, tmp_path, monkeypatch):
    hub, counter = stub_hub
    hub.reject_first_token = True
    monkeypatch.setattr("harbor.storage.resumable.RESUMABLE_UPLOAD_CHUNK_SIZE", 5)
    source = tmp_path / "payload"
    source.write_bytes(b"round-trip-data")

    await upload_resumable_file(source, "object.bin", bucket="results")

    assert bytes(hub.objects["1"]) == source.read_bytes()
    assert counter.read_text() == "2"
    assert hub.paths.count("/hub/storage/v1/upload/resumable/1") == 4


@pytest.mark.asyncio
async def test_consecutive_patch_401s_are_reported(stub_hub, tmp_path):
    hub, counter = stub_hub
    hub.reject_next_patches = 2
    source = tmp_path / "payload"
    source.write_bytes(b"payload")

    with pytest.raises(httpx.HTTPStatusError, match="401"):
        await upload_resumable_file(source, "object.bin", bucket="results")

    assert counter.read_text() == "2"
    assert len([path for path in hub.paths if path.endswith("/1")]) == 2


@pytest.mark.asyncio
async def test_sidecar_resume_starts_at_server_offset(stub_hub, tmp_path, monkeypatch):
    hub, _counter = stub_hub
    monkeypatch.setattr("harbor.storage.resumable.RESUMABLE_UPLOAD_CHUNK_SIZE", 4)
    source = tmp_path / "payload"
    payload = b"resume-from-offset"
    source.write_bytes(payload)
    hub.objects["saved"] = bytearray(payload[:7])
    sidecar = source.with_suffix(".tus-url")
    sidecar.write_text(hub.base_url + "/hub/storage/v1/upload/resumable/saved")

    await upload_resumable_file(source, "object.bin", bucket="results")

    assert bytes(hub.objects["saved"]) == payload
    assert hub.patch_offsets == [7, 11, 15]
    assert "/hub/storage/v1/upload/resumable/saved" in hub.paths
    assert not sidecar.exists()
