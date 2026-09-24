"""Persist unique upload labels for selecting Flow assets through the UI."""
import json
import uuid
from agent import config


def _path(media_id: str):
    return config.BASE_DIR / 'data' / 'ui-assets' / (str(uuid.UUID(media_id)) + '.json')


def remember(media_id: str, project_id: str, name: str):
    path = _path(media_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps({'project_id': project_id, 'name': name}), encoding='utf-8')
    temp.replace(path)


def lookup(media_id: str, project_id: str) -> str:
    try:
        data = json.loads(_path(media_id).read_text(encoding='utf-8'))
        return data['name'] if data['project_id'] == project_id else ''
    except (OSError, ValueError, KeyError, TypeError):
        return ''
