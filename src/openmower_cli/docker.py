from contextlib import contextmanager
import io
import json
import subprocess
import tarfile
import docker
from docker.models.containers import Container
from docker import errors as docker_errors

from openmower_cli.constants import DEFAULT_SERVICE, DOCKER_BIN, STACK_NAME, COMPOSE_FILE

client = docker.from_env()

_file_cache: dict[tuple[str, str], str | None] = {}
_folder_cache: dict[tuple[str, str], dict[str, str]] = {}

def get_compose_config():
    result = subprocess.run([DOCKER_BIN, "compose", "-f", COMPOSE_FILE, "config", "--format", "json"], capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Failed to get image name: {result.stderr}")
    return json.loads(result.stdout)

def get_image_name(service=DEFAULT_SERVICE):
    config = get_compose_config()
    return config["services"][service]["image"]

def get_container(service=DEFAULT_SERVICE, include_stopped=False):
    containers = client.containers.list(
        all=include_stopped,
        filters={
        "label": [
            f"com.docker.compose.project={STACK_NAME}",
            f"com.docker.compose.service={service}"
        ]
    })
    return containers[0] if containers else None

@contextmanager
def temp_container_for_image(image_name: str):
    container = client.containers.create(image_name)
    try:
        yield container
    finally:
        container.remove(force=True)

@contextmanager
def fetch_from_container(container, path):
    try:
        bits, _ = container.get_archive(path)
    except docker_errors.NotFound:
        yield None
        return

    fileobj = io.BytesIO()
    for chunk in bits:
        fileobj.write(chunk)
    fileobj.seek(0)

    with tarfile.open(fileobj=fileobj) as tar:
        members = tar.getmembers()
        if not members:
            yield None
            return

        yield tar
        return

def fetch_file_from_container(container: Container, path: str):
    with fetch_from_container(container, path) as tar:
        if tar is None:
            return None
        first_member = tar.getmembers()[0]
        f = tar.extractfile(first_member)
        return f.read().decode('utf-8') if f else None

# Returns a dictionary of file paths to file contents
def fetch_folder_from_container(container: Container, path: str):
    with fetch_from_container(container, path) as tar:
        if tar is None:
            return
        members = tar.getmembers()
        base_path_len = len(members[0].name) + 1
        for member in members:
            if not member.isfile():
                continue
            f = tar.extractfile(member)
            if f:
                rel_path = member.name[base_path_len:]
                content = f.read().decode('utf-8')
                yield rel_path, content

def fetch_file_from_image(path: str, service=DEFAULT_SERVICE):
    image_name = get_image_name(service)
    image = client.images.get(image_name)
    if image.id is None:
        raise docker_errors.ImageNotFound(image_name)

    cache_key = (image.id, path)
    if cache_key in _file_cache:
        return _file_cache[cache_key]

    with temp_container_for_image(image_name) as container:
        content = fetch_file_from_container(container, path)
        _file_cache[cache_key] = content
        return content

def fetch_folder_from_image(path: str, service=DEFAULT_SERVICE):
    image_name = get_image_name(service)
    image = client.images.get(image_name)
    if image.id is None:
        raise docker_errors.ImageNotFound(image_name)

    cache_key = (image.id, path)
    if cache_key in _folder_cache:
        return _folder_cache[cache_key].items()

    with temp_container_for_image(image_name) as container:
        results = dict(fetch_folder_from_container(container, path))
        _folder_cache[cache_key] = results
        return results.items()
