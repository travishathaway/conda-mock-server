from pathlib import Path

from flask import Flask, abort, send_file

_CONTENT_TYPES: dict[str, str] = {
    ".conda": "application/x-conda-package",
    ".json": "application/json",
    ".zst": "application/zstd",
    ".bz2": "application/x-bz2",
    ".txt": "text/plain",
}


def _mime_for(path: Path) -> str:
    # Check compound suffixes first (e.g. .msgpack.zst, .json.zst)
    suffixes = "".join(path.suffixes)
    for ext, mime in _CONTENT_TYPES.items():
        if suffixes.endswith(ext):
            return mime
    return "application/octet-stream"


def create_app(data_root: Path) -> Flask:
    app = Flask(__name__)

    @app.route("/<path:filepath>")
    def serve_file(filepath: str):
        target = (data_root / filepath).resolve()
        # Guard against path traversal outside data_root
        try:
            target.relative_to(data_root.resolve())
        except ValueError:
            abort(403)
        if not target.exists() or not target.is_file():
            abort(404)
        return send_file(target, mimetype=_mime_for(target))

    return app
