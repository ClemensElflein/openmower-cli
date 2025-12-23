import os

from jsonrpcserver import Error, Result, Success, method

from openmower_cli.constants import CONTAINER_WORKSPACE_PATH, HOST_WORKSPACE_PATH
from openmower_cli.docker import fetch_file_from_image, fetch_folder_from_image
from openmower_cli.helpers import fetch_file_locally, fetch_folder_locally

@method(name="meta.rpc.ping")
def ping() -> Result:
    return Success("pong")

@method(name="meta.config.schema")
def config_schema() -> Result:
    path: str | None = None
    content: str | None = None
    source: str | None = None

    if os.path.exists(HOST_WORKSPACE_PATH):
        source = "on host"
        path = HOST_WORKSPACE_PATH + '/config/schema.json'
        content = fetch_file_locally(path)
    else:
        source = "in container"
        path = CONTAINER_WORKSPACE_PATH + '/config/schema.json'
        content = fetch_file_from_image(path)

    if not content:
        return Error(2, f"{path} not found {source}")
    return Success(content)

@method(name="meta.config.defaults")
def config_defaults() -> Result:
    path: str | None = None
    content: dict[str, str] | None = None
    source: str | None = None

    if os.path.exists(HOST_WORKSPACE_PATH):
        source = "on host"
        path = HOST_WORKSPACE_PATH + '/config/defaults'
        content = dict(fetch_folder_locally(path))
    else:
        source = "in container"
        path = CONTAINER_WORKSPACE_PATH + '/config/defaults'
        content = dict(fetch_folder_from_image(path))


    if not content:
        return Error(2, f"{path} not found {source}")
    return Success(content)
