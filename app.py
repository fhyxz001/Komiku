#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
漫画文件夹管理 — 最简版后端
扫描指定目录下所有子文件夹大小，提供删除接口。
零第三方依赖，仅使用 Python 标准库。

配置（环境变量）:
  MANGA_DIR  漫画根目录，默认 /vol1/1000/Manga
  HOST       监听地址，默认 0.0.0.0
  PORT       监听端口，默认 8080
  MOCK=1     使用模拟数据（不执行 du，用于本地预览/调试）

运行:
  python app.py
  MOCK=1 python app.py          # 本地预览（无 NAS 时）
  MANGA_DIR=/data/Manga python app.py
"""

import json
import os
import shutil
import subprocess
import glob
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ---------------- 配置 ----------------
MANGA_DIR = os.environ.get("MANGA_DIR", "/vol1/1000/Manga")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))
MOCK = os.environ.get("MOCK", "").lower() in ("1", "true", "yes")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

# 模拟数据（MOCK 模式使用）
_MOCK_FOLDERS = [
    ("One Piece 卷1-100", 28.5 * 1024**3),
    ("海贼王 全集", 19.2 * 1024**3),
    ("进击的巨人", 12.8 * 1024**3),
    ("鬼灭之刃", 8.4 * 1024**3),
    ("咒术回战", 7.1 * 1024**3),
    ("间谍过家家", 3.6 * 1024**3),
    ("短篇合集", 1.2 * 1024**3),
    ("电锯人", 0.8 * 1024**3),
    ("测试空目录", 0.0),
]


def scan_folders():
    """执行 du 扫描 MANGA_DIR 下所有子文件夹，返回按大小降序的列表。

    使用 `du -sb <每个子目录>` 获取精确字节数（比 --block-size=G 更精确，
    前端再换算为 GB/MB 显示）。原指令 du -sh --block-size=G 会四舍五入到整 G，
    小文件夹会全部显示为 1G，丢失分辨率，故改用字节模式。
    """
    if MOCK:
        return [{"name": n, "path": os.path.join(MANGA_DIR, n), "size_bytes": int(s)}
                for n, s in _MOCK_FOLDERS]

    manga_path = Path(MANGA_DIR)
    if not manga_path.is_dir():
        raise FileNotFoundError(f"目录不存在或不可访问: {MANGA_DIR}")

    # 列出直接子目录（含隐藏目录），du 对每个子目录统计
    subdirs = [d for d in glob.glob(os.path.join(MANGA_DIR, "*")) if os.path.isdir(d)]
    if not subdirs:
        return []

    # du -sb：精确字节数。timeout 防止超大目录卡死。
    result = subprocess.run(
        ["du", "-sb"] + subdirs,
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        # du 可能因个别目录权限报错但仍有部分输出，尝试继续解析
        if not result.stdout.strip():
            raise RuntimeError(f"du 执行失败: {result.stderr.strip() or '未知错误'}")

    folders = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        try:
            size_bytes = int(parts[0])
        except ValueError:
            continue
        full_path = parts[1].rstrip("/").rstrip("\\")
        name = os.path.basename(full_path)
        if not name:
            continue
        folders.append({"name": name, "path": full_path, "size_bytes": size_bytes})

    folders.sort(key=lambda x: x["size_bytes"], reverse=True)
    return folders


def safe_target(name):
    """校验文件夹名合法性，返回绝对路径。拒绝路径越界。"""
    if not name or name in (".", ".."):
        raise ValueError("非法文件夹名")
    if "/" in name or "\\" in name or "\x00" in name:
        raise ValueError("非法文件夹名")

    base = os.path.realpath(MANGA_DIR)
    target = os.path.realpath(os.path.join(MANGA_DIR, name))
    # 必须是 MANGA_DIR 的直接子目录
    if os.path.dirname(target) != base:
        raise ValueError("路径越界")
    return target


def delete_folder(name):
    """删除 MANGA_DIR 下的直接子文件夹。"""
    # 始终校验名称合法性 + 路径越界防护（MOCK 模式同样校验）
    target = safe_target(name)
    if MOCK:
        # 模拟模式下仅从内存列表移除（重启后恢复），不触碰真实文件
        global _MOCK_FOLDERS
        _MOCK_FOLDERS = [(n, s) for n, s in _MOCK_FOLDERS if n != name]
        return
    if not os.path.isdir(target):
        raise FileNotFoundError("文件夹不存在")
    shutil.rmtree(target)


# ---------------- HTTP ----------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # 简化日志
        print(f"[{self.command}] {self.path} - {args[1] if len(args) > 1 else ''}")

    def _send_json(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_text(self, code, text, ctype="text/plain; charset=utf-8"):
        data = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_static(self, rel):
        path = (STATIC_DIR / rel).resolve()
        # 防目录穿越
        try:
            path.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self._send_text(403, "Forbidden")
            return
        if not path.is_file():
            self._send_text(404, "Not Found")
            return
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".ico": "image/x-icon",
        }.get(path.suffix.lower(), "application/octet-stream")
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._serve_static("index.html")
        elif path == "/api/folders":
            try:
                folders = scan_folders()
                total = sum(f["size_bytes"] for f in folders)
                self._send_json(200, {
                    "ok": True,
                    "dir": MANGA_DIR,
                    "mock": MOCK,
                    "count": len(folders),
                    "total_bytes": total,
                    "folders": folders,
                })
            except FileNotFoundError as e:
                self._send_json(404, {"ok": False, "error": str(e)})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": f"扫描失败: {e}"})
        else:
            self._send_text(404, "Not Found")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != "/api/delete":
            self._send_json(404, {"ok": False, "error": "Not Found"})
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "请求体非合法 JSON"})
            return
        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            self._send_json(400, {"ok": False, "error": "缺少 name 字段"})
            return
        try:
            delete_folder(name.strip())
            self._send_json(200, {"ok": True, "deleted": name.strip()})
        except FileNotFoundError as e:
            self._send_json(404, {"ok": False, "error": str(e)})
        except ValueError as e:
            self._send_json(400, {"ok": False, "error": str(e)})
        except Exception as e:
            self._send_json(500, {"ok": False, "error": f"删除失败: {e}"})


def main():
    print("=" * 50)
    print("漫画文件夹管理服务")
    print(f"  MANGA_DIR : {MANGA_DIR}")
    print(f"  MOCK 模式 : {'开启（模拟数据）' if MOCK else '关闭'}")
    print(f"  监听      : http://{HOST}:{PORT}")
    print("=" * 50)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
