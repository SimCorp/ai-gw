"""ACA-Jobs spawn for scanner tool containers (nmap/nuclei/ZAP/garak).

Mirrors the Azure-only spawn used by the workflow-worker: instead of running a
sibling Docker container and capturing its stdout, we start a manual execution
of a pre-declared ACA job (``SCANNER_RUNNER_JOB_NAME``) with a per-execution
template override carrying the tool image + command, then poll to completion.

Output exchange is via an **Azure Files** share mounted at /run inside the job
container: each tool writes its findings to a per-execution file on the share
(callers pass an output path under /run, e.g. ``-oX /run/<token>/out.xml``),
which we read back and hand to the existing parser unchanged.

Storage data plane uses ``DefaultAzureCredential`` (scanner managed identity)
with ``token_intent="backup"`` for AAD on SMB shares.

The Azure SDK clients are referenced via module-level names so unit tests can
monkeypatch them without real credentials or network I/O.
"""

from __future__ import annotations

import logging
import time
import uuid

from azure.identity import DefaultAzureCredential
from azure.mgmt.appcontainers import ContainerAppsAPIClient
from azure.mgmt.appcontainers import models as aca_models
from azure.storage.fileshare import ShareServiceClient

from app.config import settings

log = logging.getLogger(__name__)

_TERMINAL_STATES = {"Succeeded", "Failed", "Degraded", "Stopped"}

_client = None
_share = None
_credential = None


def _ensure_clients():
    global _client, _share, _credential
    if _client is not None:
        return
    if not (
        settings.scanner_runner_job_name
        and settings.azure_resource_group
        and settings.azure_subscription_id
        and settings.runs_share_name
        and settings.runs_storage_account
    ):
        raise ValueError(
            "ACA scanner runtime requires SCANNER_RUNNER_JOB_NAME, AZURE_RESOURCE_GROUP, "
            "AZURE_SUBSCRIPTION_ID, AIGW_RUNS_SHARE and AIGW_RUNS_STORAGE_ACCOUNT"
        )
    _credential = DefaultAzureCredential()
    _client = ContainerAppsAPIClient(_credential, settings.azure_subscription_id)
    _share = ShareServiceClient(
        account_url=f"https://{settings.runs_storage_account}.file.core.windows.net",
        credential=_credential,
        token_intent="backup",
    ).get_share_client(settings.runs_share_name)


def run_tool_via_aca(
    image: str,
    command: list[str],
    output_file: str,
    *,
    timeout: int = None,
) -> str:
    """Start an ACA job execution for a scanner tool and return its output.

    ``output_file`` is the share-relative path (under the run token dir) the
    tool was told to write to (e.g. ``<token>/out.xml``). Callers build the
    matching ``/run/<token>/out.xml`` argument into ``command``.

    Returns the file content (decoded) or "" if nothing was produced.
    """
    _ensure_clients()
    if timeout is None:
        timeout = settings.max_container_timeout_seconds

    token = output_file.split("/", 1)[0]
    try:
        _share.get_directory_client(token).create_directory()
    except Exception:
        pass

    container = aca_models.JobExecutionContainer(
        image=image,
        name="tool",
        command=command,
    )
    template = aca_models.JobExecutionTemplate(containers=[container])

    poller = _client.jobs.begin_start(
        settings.azure_resource_group, settings.scanner_runner_job_name, template=template
    )
    execution = poller.result()
    execution_name = execution.name
    log.info("started scanner aca execution %s (image=%s)", execution_name, image)

    status = _poll_until_terminal(execution_name, timeout)
    if status != "Succeeded":
        log.warning("scanner aca execution %s ended with status=%s", execution_name, status)

    output = _read_output(output_file)
    _cleanup(token)
    return output


def _poll_until_terminal(execution_name: str, timeout: int) -> str:
    deadline = time.monotonic() + timeout
    while True:
        for ex in _client.jobs_executions.list(
            settings.azure_resource_group, settings.scanner_runner_job_name
        ):
            if ex.name == execution_name and ex.status is not None:
                status = str(ex.status)
                if status in _TERMINAL_STATES:
                    return status
        if time.monotonic() >= deadline:
            try:
                _client.jobs.begin_stop_execution(
                    settings.azure_resource_group,
                    settings.scanner_runner_job_name,
                    execution_name,
                ).result()
            except Exception:
                pass
            return "Stopped"
        time.sleep(settings.scanner_aca_poll_interval_s)


def _read_output(output_file: str) -> str:
    token, _, name = output_file.partition("/")
    try:
        stream = _share.get_directory_client(token).get_file_client(name).download_file()
        return stream.readall().decode("utf-8", errors="replace")
    except Exception as exc:
        log.warning("failed to read scanner output %s: %s", output_file, exc)
        return ""


def _cleanup(token: str) -> None:
    try:
        dir_client = _share.get_directory_client(token)
        for f in list(dir_client.list_directories_and_files()):
            try:
                dir_client.delete_file(f["name"])
            except Exception:
                pass
        dir_client.delete_directory()
    except Exception:
        pass


def new_run_token() -> str:
    return uuid.uuid4().hex[:16]
