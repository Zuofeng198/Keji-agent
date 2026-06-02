"""压缩包工具 —— 创建/解压/浏览 zip/7z/tar/rar"""

import os
import json
import zipfile
import tarfile
import tempfile
from typing import Optional

from core.tools import register_tool


def _format_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def _ensure_output_dir(path: str) -> str:
    """确保输出目录存在，不存在则创建"""
    from core.path_policy import check_path
    path, err = check_path(path)
    if err:
        raise ValueError(err.replace("错误：", ""))
    os.makedirs(path, exist_ok=True)
    return path


def _detect_format(path: str) -> str:
    """根据文件扩展名检测压缩格式"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".zip":
        return "zip"
    if ext in (".tar", ".gz", ".tgz", ".bz2", ".xz"):
        return "tar"
    if ext == ".7z":
        return "7z"
    if ext in (".rar", ".cbr"):
        return "rar"
    return "zip"


def _list_zip(zf: zipfile.ZipFile) -> str:
    items = []
    for info in zf.infolist():
        is_dir = info.filename.endswith("/")
        size = _format_size(info.file_size) if not is_dir else "-"
        compress = _format_size(info.compress_size) if not is_dir else "-"
        ratio = f"{info.compress_size / info.file_size * 100:.0f}%" if info.file_size > 0 else "-"
        items.append(f"  {'📁' if is_dir else '📄'} {info.filename}  ({size} → {compress}, {ratio})")
    return "\n".join(items)


def _list_tar(tf: tarfile.TarFile) -> str:
    items = []
    for info in tf.getmembers():
        is_dir = info.isdir()
        size = _format_size(info.size) if not is_dir else "-"
        items.append(f"  {'📁' if is_dir else '📄'} {info.name}  ({size})")
    return "\n".join(items)


# ═══════════════════════════════════════════════════════════════
# 工具：浏览压缩包内容
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="browse_archive",
    description="浏览压缩包内容（列出 zip/7z/tar/rar 内部的文件列表），不解压",
    parameters={
        "path": {"type": "string", "description": "压缩包文件完整路径"},
    },
    category="filesystem",
    timeout=15,
)
def browse_archive(path: str) -> str:
    from core.path_policy import check_path
    path, err = check_path(path, must_exist=True, must_be_file=True)
    if err:
        return err
    if not os.path.isfile(path):
        return f"错误：文件不存在「{path}」"

    fmt = _detect_format(path)
    size = _format_size(os.path.getsize(path))
    try:
        if fmt == "zip":
            with zipfile.ZipFile(path, "r") as zf:
                items = _list_zip(zf)
                total = len(zf.infolist())
                dirs = sum(1 for i in zf.infolist() if i.filename.endswith("/"))
                return (
                    f"📦 压缩包: {os.path.basename(path)}\n"
                    f"格式: ZIP | 大小: {size} | 包含: {total} 项 ({dirs} 个文件夹)\n\n{items}"
                )
        elif fmt == "tar":
            with tarfile.open(path, "r") as tf:
                items = _list_tar(tf)
                total = len(tf.getmembers())
                dirs = sum(1 for m in tf.getmembers() if m.isdir())
                return (
                    f"📦 压缩包: {os.path.basename(path)}\n"
                    f"格式: TAR | 大小: {size} | 包含: {total} 项 ({dirs} 个文件夹)\n\n{items}"
                )
        elif fmt == "7z":
            return _browse_7z(path, size)
        elif fmt == "rar":
            return _browse_rar(path, size)
        else:
            return f"错误：不支持的压缩格式「{fmt}」"
    except zipfile.BadZipFile:
        return f"错误：无效的 ZIP 文件「{path}」"
    except tarfile.ReadError:
        return f"错误：无效的 TAR 文件「{path}」"
    except Exception as e:
        return f"读取压缩包失败: {str(e)[:200]}"


def _browse_7z(path: str, size_str: str) -> str:
    try:
        import py7zr
    except ImportError:
        return f"错误：请先安装 py7zr 库（pip install py7zr）以支持 7z 格式"

    with py7zr.SevenZipFile(path, "r") as szf:
        all_info = szf.list()
        items = []
        for info in all_info:
            is_dir = info.is_directory
            sz = _format_size(info.uncompressed) if not is_dir else "-"
            items.append(f"  {'📁' if is_dir else '📄'} {info.filename}  ({sz})")
        total = len(all_info)
    return (
        f"📦 压缩包: {os.path.basename(path)}\n"
        f"格式: 7z | 大小: {size_str} | 包含: {total} 项\n\n" + "\n".join(items)
    )


def _browse_rar(path: str, size_str: str) -> str:
    try:
        import rarfile
    except ImportError:
        return f"错误：请先安装 rarfile 库（pip install rarfile）以支持 RAR 格式"

    with rarfile.RarFile(path, "r") as rf:
        items = []
        for info in rf.infolist():
            is_dir = info.isdir()
            sz = _format_size(info.file_size) if not is_dir else "-"
            items.append(f"  {'📁' if is_dir else '📄'} {info.filename}  ({sz})")
        total = len(rf.infolist())
    return (
        f"📦 压缩包: {os.path.basename(path)}\n"
        f"格式: RAR | 大小: {size_str} | 包含: {total} 项\n\n" + "\n".join(items)
    )


# ═══════════════════════════════════════════════════════════════
# 工具：解压压缩包
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="extract_archive",
    description="解压压缩包到指定目录（支持 zip/7z/tar/tar.gz/tar.bz2/rar），可设密码",
    parameters={
        "path": {"type": "string", "description": "压缩包文件完整路径"},
        "output_dir": {
            "type": "string",
            "description": "解压目标目录，默认解压到压缩包所在目录的以文件名命名的文件夹",
        },
        "password": {
            "type": "string",
            "description": "解压密码（可选），仅支持 ZIP 加密",
        },
    },
    category="filesystem",
    timeout=120,
)
def extract_archive(path: str, output_dir: str = "", password: str = "") -> str:
    from core.path_policy import check_path
    path, err = check_path(path, must_exist=True, must_be_file=True)
    if err:
        return err
    if not os.path.isfile(path):
        return f"错误：文件不存在「{path}」"

    if not output_dir:
        base = os.path.splitext(os.path.basename(path))[0]
        output_dir = os.path.join(os.path.dirname(path), base)
    try:
        output_dir = _ensure_output_dir(output_dir)
    except ValueError as e:
        return f"错误：{e}"

    fmt = _detect_format(path)
    try:
        if fmt == "zip":
            return _extract_zip(path, output_dir, password)
        elif fmt == "tar":
            return _extract_tar(path, output_dir)
        elif fmt == "7z":
            return _extract_7z(path, output_dir, password)
        elif fmt == "rar":
            return _extract_rar(path, output_dir)
        else:
            return f"错误：不支持的压缩格式「{fmt}」"
    except Exception as e:
        return f"解压失败: {str(e)[:300]}"


def _extract_zip(path: str, output_dir: str, password: str = "") -> str:
    with zipfile.ZipFile(path, "r") as zf:
        pwd = password.encode("utf-8") if password else None
        try:
            zf.extractall(output_dir, pwd=pwd)
        except RuntimeError as e:
            if "password" in str(e).lower() or "encrypted" in str(e).lower():
                return f"错误：文件加密需要密码，请提供正确的解压密码"
            raise
        total = len(zf.infolist())
        dirs = sum(1 for i in zf.infolist() if i.filename.endswith("/"))
    return f"✅ 解压完成！\n文件: {path}\n目标: {output_dir}\n共 {total} 项 ({dirs} 个文件夹)"


def _extract_tar(path: str, output_dir: str) -> str:
    with tarfile.open(path, "r") as tf:
        tf.extractall(output_dir)
        total = len(tf.getmembers())
    return f"✅ 解压完成！\n文件: {path}\n目标: {output_dir}\n共 {total} 项"


def _extract_7z(path: str, output_dir: str, password: str = "") -> str:
    try:
        import py7zr
    except ImportError:
        return f"错误：请先安装 py7zr 库（pip install py7zr）以支持 7z 格式"

    with py7zr.SevenZipFile(path, "r", password=password) as szf:
        szf.extractall(output_dir)
        total = len(szf.list())
    return f"✅ 解压完成！\n文件: {path}\n目标: {output_dir}\n共 {total} 项"


def _extract_rar(path: str, output_dir: str) -> str:
    try:
        import rarfile
    except ImportError:
        return f"错误：请先安装 rarfile 库（pip install rarfile）以支持 RAR 格式"

    with rarfile.RarFile(path, "r") as rf:
        rf.extractall(output_dir)
        total = len(rf.infolist())
    return f"✅ 解压完成！\n文件: {path}\n目标: {output_dir}\n共 {total} 项"


# ═══════════════════════════════════════════════════════════════
# 工具：创建压缩包
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="create_archive",
    description="创建压缩包（支持 zip/tar.gz/tar.bz2/7z），可将多个文件或文件夹打包",
    parameters={
        "sources": {
            "type": "string",
            "description": "要压缩的文件或文件夹路径，多个用 | 分隔，如 D:\\doc\\a.txt|D:\\doc\\folder",
        },
        "output_path": {
            "type": "string",
            "description": "输出压缩包路径（含文件名和扩展名），如 D:\\backup\\归档.zip",
        },
        "format": {
            "type": "string",
            "description": "压缩格式：zip（默认）、tar.gz、tar.bz2、7z",
        },
        "password": {
            "type": "string",
            "description": "加密密码（仅 ZIP/7z 支持加密），可选",
        },
    },
    category="filesystem",
    timeout=120,
)
def create_archive(sources: str, output_path: str = "", format: str = "zip") -> str:
    source_list = [s.strip() for s in sources.split("|") if s.strip()]
    if not source_list:
        return "错误：请至少提供一个要压缩的文件或文件夹路径"

    from core.path_policy import check_path
    valid_sources = []
    for s in source_list:
        resolved, err = check_path(s, must_exist=True)
        if err:
            return err
        valid_sources.append(resolved)

    return _do_create_archive(valid_sources, output_path, format)


def _do_create_archive(sources: list, output_path: str, fmt: str) -> str:
    fmt = fmt.lower().strip()
    if fmt not in ("zip", "tar.gz", "tar.bz2", "7z"):
        fmt = "zip"

    # 自动补齐扩展名
    from core.path_policy import check_path, default_browse_path
    if not output_path:
        base_dir = default_browse_path()
        ext_map = {"zip": ".zip", "tar.gz": ".tar.gz", "tar.bz2": ".tar.bz2", "7z": ".7z"}
        output_path = os.path.join(base_dir, f"归档{ext_map[fmt]}")
    else:
        output_path, err = check_path(output_path)
        if err:
            return err

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    try:
        if fmt == "zip":
            return _create_zip(sources, output_path)
        elif fmt in ("tar.gz", "tar.bz2"):
            return _create_tar(sources, output_path, fmt)
        elif fmt == "7z":
            return _create_7z(sources, output_path)
    except Exception as e:
        return f"创建压缩包失败: {str(e)[:300]}"
    return f"错误：不支持的格式「{fmt}」"


def _create_zip(sources: list, output_path: str) -> str:
    count = 0
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for src in sources:
            if os.path.isdir(src):
                for root, dirs, files in os.walk(src):
                    for fn in files:
                        full = os.path.join(root, fn)
                        arcname = os.path.relpath(full, os.path.dirname(src))
                        zf.write(full, arcname)
                        count += 1
            else:
                zf.write(src, os.path.basename(src))
                count += 1
    size = _format_size(os.path.getsize(output_path))
    return f"✅ 压缩包已创建！\n路径: {output_path}\n大小: {size}\n包含: {count} 个文件\n格式: ZIP"


def _create_tar(sources: list, output_path: str, fmt: str) -> str:
    mode = "w:gz" if fmt == "tar.gz" else "w:bz2"
    count = 0
    with tarfile.open(output_path, mode) as tf:
        for src in sources:
            if os.path.isdir(src):
                tf.add(src, arcname=os.path.basename(src))
                for root, dirs, files in os.walk(src):
                    count += len(files)
            else:
                tf.add(src, arcname=os.path.basename(src))
                count += 1
    size = _format_size(os.path.getsize(output_path))
    return f"✅ 压缩包已创建！\n路径: {output_path}\n大小: {size}\n包含: {count} 个文件\n格式: {fmt}"


def _create_7z(sources: list, output_path: str) -> str:
    try:
        import py7zr
    except ImportError:
        return f"错误：请先安装 py7zr 库（pip install py7zr）以支持 7z 格式"

    count = 0
    with py7zr.SevenZipFile(output_path, "w") as szf:
        for src in sources:
            if os.path.isdir(src):
                szf.write(src, arcname=os.path.basename(src))
                for root, dirs, files in os.walk(src):
                    count += len(files)
            else:
                szf.write(src, arcname=os.path.basename(src))
                count += 1
    size = _format_size(os.path.getsize(output_path))
    return f"✅ 压缩包已创建！\n路径: {output_path}\n大小: {size}\n包含: {count} 个文件\n格式: 7z"
