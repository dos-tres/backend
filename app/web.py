"""FE 빌드 화면(React dist)을 API와 같은 주소에서 제공한다 (배포: 이미지 1개, docs/DEPLOYMENT.md).

- WEB_DIR(환경변수)에 index.html 이 있을 때만 켠다. 로컬 개발은 Vite 개발 서버를 쓰므로 보통 비워 둔다.
- /api/* 는 API 라우터가 먼저 받는다. 없는 /api/* 는 화면이 아니라 JSON 404.
- 그 밖의 없는 경로는 index.html (새로고침해도 화면이 뜨게).
"""
from __future__ import annotations

from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class SPAFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope):
        first = path.replace("\\", "/").split("/", 1)[0]   # Windows 에서는 경로가 역슬래시로 온다
        if first == "api":
            raise HTTPException(status_code=404)
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            response = None
        if response is None or response.status_code == 404:
            response = await super().get_response("index.html", scope)
        if path in ("", ".", "index.html") or response.media_type == "text/html":
            response.headers["Cache-Control"] = "no-cache"   # 새 배포가 바로 보이게 (assets/ 는 해시 이름이라 캐시 가능)
        return response


def web_files(web_dir: str) -> SPAFiles | None:
    if not web_dir or not (Path(web_dir) / "index.html").is_file():
        return None
    return SPAFiles(directory=web_dir, html=True)
