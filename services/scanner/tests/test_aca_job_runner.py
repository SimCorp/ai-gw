"""Unit tests for the scanner ACA-Jobs tool runner with the Azure SDK mocked.

Asserts:
- run_tool_via_aca starts a job execution with the expected job name + tool
  image + command override,
- the tool's output file is read back from the share and returned,
- timeout/non-success status still returns whatever output exists.
"""

from __future__ import annotations

# NOTE: `app.*` is imported lazily inside helpers/tests (not at module top) —
# multiple services share the `app` package name and the root services/conftest.py
# re-points sys.path per-test.


class _FakeExecution:
    def __init__(self, name, status):
        self.name = name
        self.status = status


class _FakePoller:
    def __init__(self, result):
        self._result = result

    def result(self):
        return self._result


class _FakeJobsOps:
    def __init__(self, statuses):
        self._statuses = list(statuses)
        self.started = []
        self.stopped = []

    def begin_start(self, rg, job_name, template=None):
        self.started.append((rg, job_name, template))
        return _FakePoller(_FakeExecution("exec-1", "Running"))

    def begin_stop_execution(self, rg, job_name, execution_name):
        self.stopped.append(execution_name)
        return _FakePoller(None)


class _FakeJobsExecutionsOps:
    def __init__(self, jobs):
        self._jobs = jobs

    def list(self, rg, job_name):
        s = self._jobs._statuses
        status = s.pop(0) if len(s) > 1 else s[0]
        return [_FakeExecution("exec-1", status)]


class _FakeClient:
    def __init__(self, statuses):
        self.jobs = _FakeJobsOps(statuses)
        self.jobs_executions = _FakeJobsExecutionsOps(self.jobs)


class _FakeFile:
    def __init__(self, store, key):
        self._store = store
        self._key = key

    def download_file(self):
        store, key = self._store, self._key

        class _S:
            def readall(self_inner):
                if key not in store:
                    raise FileNotFoundError(key)
                return store[key]

        return _S()


class _FakeDir:
    def __init__(self, store, prefix):
        self._store = store
        self._prefix = prefix

    def create_directory(self):
        pass

    def get_file_client(self, name):
        return _FakeFile(self._store, f"{self._prefix}/{name}")

    def list_directories_and_files(self):
        return []

    def delete_file(self, name):
        self._store.pop(f"{self._prefix}/{name}", None)

    def delete_directory(self):
        pass


class _FakeShare:
    def __init__(self, store):
        self._store = store

    def get_directory_client(self, path):
        return _FakeDir(self._store, path)


def _configure(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "scanner_container_runtime", "aca_job")
    monkeypatch.setattr(settings, "scanner_runner_job_name", "job-scanner-runner-test-sdc")
    monkeypatch.setattr(settings, "azure_resource_group", "rg-test")
    monkeypatch.setattr(settings, "azure_subscription_id", "sub-test")
    monkeypatch.setattr(settings, "runs_share_name", "aigw-runs")
    monkeypatch.setattr(settings, "runs_storage_account", "stsdctest")
    monkeypatch.setattr(settings, "scanner_aca_poll_interval_s", 0.001)


def _patch_clients(monkeypatch, statuses, store):
    import app.worker.aca_job_runner as runner_mod

    client = _FakeClient(statuses)
    share = _FakeShare(store)
    # Bypass _ensure_clients() lazy build by setting module globals directly.
    monkeypatch.setattr(runner_mod, "_client", client)
    monkeypatch.setattr(runner_mod, "_share", share)
    monkeypatch.setattr(runner_mod, "_credential", object())
    return client


def test_run_tool_via_aca_starts_and_reads_output(monkeypatch):
    import app.worker.aca_job_runner as runner_mod

    _configure(monkeypatch)
    store = {"tok123/nmap.xml": b"<nmaprun/>"}
    client = _patch_clients(monkeypatch, ["Succeeded"], store)

    out = runner_mod.run_tool_via_aca(
        "instrumentisto/nmap",
        ["-oX", "/run/tok123/nmap.xml", "scanme.example.com"],
        "tok123/nmap.xml",
        timeout=5,
    )

    # started with expected job name + image + command override
    assert len(client.jobs.started) == 1
    rg, job_name, template = client.jobs.started[0]
    assert rg == "rg-test"
    assert job_name == "job-scanner-runner-test-sdc"
    assert template.containers[0].image == "instrumentisto/nmap"
    assert template.containers[0].command == [
        "-oX",
        "/run/tok123/nmap.xml",
        "scanme.example.com",
    ]
    # output read back from the share
    assert out == "<nmaprun/>"


def test_run_tool_via_aca_timeout_stops_and_returns_empty(monkeypatch):
    import app.worker.aca_job_runner as runner_mod

    _configure(monkeypatch)
    store: dict[str, bytes] = {}
    client = _patch_clients(monkeypatch, ["Running"], store)

    out = runner_mod.run_tool_via_aca(
        "projectdiscovery/nuclei",
        ["-u", "http://x", "-o", "/run/tok9/nuclei.json"],
        "tok9/nuclei.json",
        timeout=0,
    )

    assert client.jobs.stopped == ["exec-1"]
    assert out == ""
