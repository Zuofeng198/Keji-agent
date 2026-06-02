"""科吉 AI 助手 — 桌面启动器

双击 exe 自动弹出桌面窗口，如果桌面窗口打不开则自动打开浏览器。
"""

import os
import sys
import threading
import asyncio
import argparse
import webbrowser


def start_desktop():
    """启动桌面应用（优先 pywebview，失败则回退到浏览器）"""
    from main import app

    # 先启动服务
    server_thread, port = _start_server(app)
    import time
    url = f"http://127.0.0.1:{port}?_t={int(time.time() * 1000)}"

    # 尝试 pywebview 桌面窗口
    try:
        import webview
        # pywebview 可用，创建桌面窗口
        webview.create_window(
            title="科吉 AI 助手",
            url=url,
            width=1280,
            height=860,
            min_size=(960, 640),
            resizable=True,
            text_select=True,
            easy_drag=False,
        )
        webview.start(debug=False)
        return  # 正常退出
    except ImportError:
        print("pywebview 未安装，自动打开浏览器...")
    except Exception as e:
        print(f"桌面窗口打开失败 ({e})，自动打开浏览器...")

    # 回退：在浏览器打开
    _open_browser(url)

    # 保持服务器运行
    print(f"科吉 AI 助手运行中: {url}")
    print("按 Ctrl+C 停止服务")
    try:
        server_thread.join()
    except KeyboardInterrupt:
        pass


def start_server_only():
    """仅启动 Web 服务并在浏览器打开"""
    from main import app
    import uvicorn

    url = "http://127.0.0.1:8000"
    print("=" * 50)
    print("  科吉 AI 助手 v1.0.0.1-Beta")
    print("=" * 50)
    print(f"  访问地址: {url}")
    print("  按 Ctrl+C 停止服务")
    print("=" * 50)

    # 自动打开浏览器
    _open_browser(url)

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


def _open_browser(url: str):
    """在浏览器中打开链接（延迟 1 秒等服务器就绪）"""
    def _delayed_open():
        import time
        time.sleep(1.5)
        try:
            webbrowser.open(url)
        except Exception:
            pass
    threading.Thread(target=_delayed_open, daemon=True).start()


def _start_server(app):
    """在后台线程中启动 uvicorn 服务器"""
    from uvicorn.config import Config
    from uvicorn.server import Server

    port = 8000

    config = Config(
        app=app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )

    ready_event = threading.Event()

    def run_server():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            config.load()
            server = Server(config=config)

            original_startup = server.startup

            async def startup_with_signal(sockets=None):
                await original_startup(sockets)
                ready_event.set()

            server.startup = startup_with_signal
            loop.run_until_complete(server.serve())
        finally:
            loop.close()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    if not ready_event.wait(timeout=15):
        print("警告: 服务器启动超时")

    return thread, port


def _log_launch_error(exc: BaseException) -> None:
    try:
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, "launcher.log")
        with open(path, "a", encoding="utf-8") as f:
            import traceback
            f.write(traceback.format_exc())
            f.write("\n")
    except Exception:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="科吉 AI 助手")
    parser.add_argument(
        "--mode",
        choices=["desktop", "web"],
        default="desktop",
        help="启动模式: desktop=桌面窗口, web=浏览器访问（默认 desktop）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="服务端口（默认 8000）",
    )
    args = parser.parse_args()

    try:
        if args.mode == "desktop":
            start_desktop()
        else:
            start_server_only()
    except Exception as e:
        _log_launch_error(e)
        raise
