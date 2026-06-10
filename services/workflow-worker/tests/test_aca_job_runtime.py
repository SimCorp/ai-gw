"""Unit tests for ACAJobRuntime with the Azure SDK mocked.

Covers:
(a) the selector picks ACAJobRuntime for AGENT_CONTAINER_RUNTIME=aca_job,
(b) a run starts a job execution with the expected job name + image override +
    inputs written to the share,
(c) outputs.json is read back and returned in RunResult,
(d) timeout handling (RUNNING forever -> asyncio.TimeoutError + stop called).
"""

from __future__ import annotations

import asyncio
import json

import pytest

# NOTE: `app.*` is imported lazily inside fixtures/tests (not at module top).
# Multiple services share the `app` package name; the root services/conftest.py
# flushes and re-points sys.path per-test, so collection-time top-level imports
# would resolve to the wrong service.

# --------------------------------------------------------------------------
# Fakes for the Azure SDK clients
# --------------------------------------------------------------------------


class _FakeCredential:
    def __init__(self, *a, **k):
        pass

    def close(self):
        pass


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
    def __init__(self, status_sequence):
        # status_sequence: list of statuses returned on successive list() polls
        self._status_sequence = list(status_sequence)
        self.started = []
        self.stopped = []

    def begin_start(self, resource_group, job_name, template=None):
        self.started.append((resource_group, job_name, template))
        return _FakePoller(_FakeExecution("exec-abc", "Running"))

    def begin_stop_execution(self, resource_group, job_name, execution_name):
        self.stopped.append((resource_group, job_name, execution_name))
        return _FakePoller(None)


class _FakeJobsExecutionsOps:
    def __init__(self, jobs_ops):
        self._jobs_ops = jobs_ops

    def list(self, resource_group, job_name):
        seq = self._jobs_ops._status_sequence
        status = seq.pop(0) if len(seq) > 1 else seq[0]
        return [_FakeExecution("exec-abc", status)]


class _FakeClient:
    def __init__(self, status_sequence):
        self.jobs = _FakeJobsOps(status_sequence)
        self.jobs_executions = _FakeJobsExecutionsOps(self.jobs)


class _FakeFileClient:
    def __init__(self, store, key):
        self._store = store
        self._key = key

    def upload_file(self, data):
        self._store[self._key] = data

    def download_file(self):
        store = self._store
        key = self._key

        class _Stream:
            def readall(self_inner):
                if key not in store:
                    raise FileNotFoundError(key)
                return store[key]

        return _Stream()


class _FakeDirClient:
    def __init__(self, store, prefix):
        self._store = store
        self._prefix = prefix

    def create_directory(self):
        pass

    def get_file_client(self, name):
        return _FakeFileClient(self._store, f"{self._prefix}/{name}")

    def delete_file(self, name):
        self._store.pop(f"{self._prefix}/{name}", None)

    def delete_directory(self):
        pass


class _FakeShareClient:
    def __init__(self, store):
        self._store = store

    def get_directory_client(self, path):
        return _FakeDirClient(self._store, path)


class _FakeShareServiceClient:
    last_kwargs = None

    def __init__(self, account_url=None, credential=None, token_intent=None, store=None):
        _FakeShareServiceClient.last_kwargs = {
            "account_url": account_url,
            "token_intent": token_intent,
        }
        self._store = store

    def get_share_client(self, share_name):
        return _FakeShareClient(self._store)


@pytest.fixture
def patched_azure(monkeypatch):
    """Patch the module-level Azure SDK symbols. Returns (client_holder, store).

    client_holder["client"] is the _FakeClient built when ACAJobRuntime is
    constructed; store is the shared in-memory file share.
    """
    import app.runtime.aca_job as aca_mod

    store: dict[str, bytes] = {}
    client_holder: dict = {"status_sequence": ["Succeeded"]}

    def _make_client(credential, subscription_id):
        c = _FakeClient(client_holder["status_sequence"])
        client_holder["client"] = c
        return c

    def _make_share(account_url=None, credential=None, token_intent=None):
        return _FakeShareServiceClient(
            account_url=account_url, credential=credential, token_intent=token_intent, store=store
        )

    monkeypatch.setattr(aca_mod, "DefaultAzureCredential", _FakeCredential)
    monkeypatch.setattr(aca_mod, "ContainerAppsAPIClient", _make_client)
    monkeypatch.setattr(aca_mod, "ShareServiceClient", _make_share)
    return client_holder, store


def _make_runtime(client_holder, status_sequence, poll_interval_s=0.001):
    from app.runtime.aca_job import ACAJobRuntime

    client_holder["status_sequence"] = status_sequence
    return ACAJobRuntime(
        job_name="job-agent-runner-test-sdc",
        resource_group="rg-test",
        subscription_id="sub-test",
        share_name="aigw-runs",
        storage_account="stsdctest",
        poll_interval_s=poll_interval_s,
    )


# --------------------------------------------------------------------------
# (a) selector
# --------------------------------------------------------------------------


def test_selector_picks_aca_job(patched_azure, monkeypatch):
    from app.config import Settings
    from app.main import make_runtime
    from app.runtime.aca_job import ACAJobRuntime

    monkeypatch.setenv("AGENT_CONTAINER_RUNTIME", "aca_job")
    cfg = Settings.from_env()
    runtime = make_runtime(cfg)
    assert isinstance(runtime, ACAJobRuntime)


async def test_selector_docker_by_default(monkeypatch):
    # aiodocker.Docker() needs a running event loop, so this case is async.
    from app.config import Settings
    from app.main import make_runtime
    from app.runtime.docker import DockerRuntime

    monkeypatch.setenv("AGENT_CONTAINER_RUNTIME", "docker")
    cfg = Settings.from_env()
    assert isinstance(make_runtime(cfg), DockerRuntime)


def test_selector_relay(monkeypatch):
    from app.config import Settings
    from app.main import make_runtime
    from app.runtime.relay import RelayRuntime

    monkeypatch.setenv("AGENT_CONTAINER_RUNTIME", "relay")
    cfg = Settings.from_env()
    assert isinstance(make_runtime(cfg), RelayRuntime)


# --------------------------------------------------------------------------
# (b)+(c) run starts execution with image override, writes inputs, reads outputs
# --------------------------------------------------------------------------


async def test_run_starts_execution_and_returns_outputs(patched_azure):
    client_holder, store = patched_azure
    runtime = _make_runtime(client_holder, ["Succeeded"])

    # Pre-seed the outputs.json the agent would have written (the runtime
    # overwrites it with {} on inputs write, so seed via a side effect on poll).
    # Simpler: monkeypatch read to return our outputs after the run by writing
    # to the store before the poll resolves. Here we patch the download to a
    # known payload by pre-populating the store key the runtime reads.
    expected_outputs = {"result": "ok", "score": 42}

    # Intercept _write_inputs so that after writing inputs we also stage outputs.
    orig_write = runtime._write_inputs

    def _write_then_stage(run_dir, inputs):
        orig_write(run_dir, inputs)
        store[f"{run_dir}/outputs.json"] = json.dumps(expected_outputs).encode("utf-8")

    runtime._write_inputs = _write_then_stage
    # Disable cleanup so we can assert on what was written to the share.
    runtime._cleanup = lambda run_dir: None

    result = await runtime.run(
        image="ghcr.io/acme/agent:1.2.3",
        env={"AIGW_RUN_ID": "run-1", "AIGW_API_KEY": "sk-test"},
        inputs={"prompt": "hello"},
        run_id="run-1",
        node_id="node-a",
        timeout_s=5.0,
    )

    # (b) execution started with expected job name + image override
    jobs = client_holder["client"].jobs
    assert len(jobs.started) == 1
    rg, job_name, template = jobs.started[0]
    assert rg == "rg-test"
    assert job_name == "job-agent-runner-test-sdc"
    assert template.containers[0].image == "ghcr.io/acme/agent:1.2.3"
    env_names = {e.name: e.value for e in template.containers[0].env}
    assert env_names["AIGW_API_KEY"] == "sk-test"
    assert env_names["AIGW_RUN_DIR"] == "run-1/node-a"

    # inputs.json written to the share
    written = json.loads(store["run-1/node-a/inputs.json"])
    assert written == {"prompt": "hello"}

    # ShareServiceClient built with backup token_intent (AAD on SMB shares)
    assert _FakeShareServiceClient.last_kwargs["token_intent"] == "backup"

    # (c) outputs read back and returned in the right shape
    assert result.exit_code == 0
    assert result.outputs == expected_outputs
    assert "Succeeded" in result.stdout_tail


# --------------------------------------------------------------------------
# (d) timeout handling
# --------------------------------------------------------------------------


async def test_run_timeout_raises_and_stops(patched_azure):
    client_holder, store = patched_azure
    # Always RUNNING -> never terminal -> wait_for must time out.
    runtime = _make_runtime(client_holder, ["Running"], poll_interval_s=0.001)

    with pytest.raises(asyncio.TimeoutError):
        await runtime.run(
            image="ghcr.io/acme/agent:1.2.3",
            env={},
            inputs={},
            run_id="run-2",
            node_id="node-b",
            timeout_s=0.05,
        )

    # stop_execution called to mirror DockerRuntime's kill()
    assert client_holder["client"].jobs.stopped == [
        ("rg-test", "job-agent-runner-test-sdc", "exec-abc")
    ]


def test_init_requires_config():
    from app.runtime.aca_job import ACAJobRuntime

    with pytest.raises(ValueError):
        ACAJobRuntime(
            job_name="",
            resource_group="rg",
            subscription_id="sub",
            share_name="s",
            storage_account="acct",
        )
