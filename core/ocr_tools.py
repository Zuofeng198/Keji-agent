"""OCR 文字识别工具 —— 图片/PDF 文字提取，支持中文"""

import os
import tempfile
from typing import Optional

from core.tools import register_tool


def _get_ocr_engine():
    """获取 OCR 引擎实例（延迟初始化 + 缓存）"""
    global _ocr_cache
    if hasattr(_get_ocr_engine, "cache"):
        return _get_ocr_engine.cache

    # 优先尝试 easyocr
    reader = None
    engine_name = ""
    try:
        import easyocr
        reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
        engine_name = "easyocr"
    except Exception:
        pass

    if reader is None:
        try:
            import pytesseract
            # 测试 tesseract 是否可用
            pytesseract.get_tesseract_version()
            reader = pytesseract
            engine_name = "tesseract"
        except Exception:
            pass

    if reader is None:
        return None, ""

    _get_ocr_engine.cache = (reader, engine_name)
    return reader, engine_name


def _ocr_with_easyocr(reader, image_path: str, lang: str) -> str:
    """使用 easyocr 识别图片文字（用 PIL 读取以支持中文路径）"""
    try:
        from PIL import Image
        import numpy as np
        img = Image.open(image_path).convert("RGB")
        img_np = np.array(img)
    except Exception as e:
        return f"读取图片失败: {str(e)[:100]}"

    results = reader.readtext(img_np)
    if not results:
        return "未识别到文字"

    lines = []
    for bbox, text, confidence in results:
        lines.append(text)
    return "\n".join(lines)


def _ocr_with_tesseract(pytesseract_mod, image_path: str, lang: str) -> str:
    """使用 pytesseract 识别图片文字"""
    try:
        from PIL import Image
        img = Image.open(image_path)

        # Tesseract 语言代码映射
        lang_map = {
            "ch_sim": "chi_sim",
            "ch_tra": "chi_tra",
            "eng": "eng",
            "jpn": "jpn",
            "kor": "kor",
        }
        # 解析 lang 参数，如 "ch_sim+eng" -> "chi_sim+eng"
        tesseract_lang = "+".join(lang_map.get(l, l) for l in lang.split("+"))

        text = pytesseract_mod.image_to_string(img, lang=tesseract_lang)
        return text.strip() or "未识别到文字"
    except Exception as e:
        return f"Tesseract 识别失败: {str(e)[:200]}"


SUPPORTED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}


def _is_supported_image(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in SUPPORTED_IMAGE_EXT


# ═══════════════════════════════════════════════════════════════
# 工具：OCR 识别单张图片
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="ocr_image",
    description="识别图片中的文字（OCR），支持中文和英文，支持 PNG/JPG/BMP/TIFF/WEBP 格式",
    parameters={
        "path": {"type": "string", "description": "图片文件完整路径（也支持 image_path 参数名）"},
        "image_path": {"type": "string", "description": "图片文件完整路径（path 的别名）"},
        "lang": {
            "type": "string",
            "description": "识别语言，ch_sim=简体中文, eng=英文, 用+连接，默认 ch_sim+eng",
        },
    },
    category="utility",
    timeout=60,
)
def ocr_image(path: str = "", image_path: str = "", lang: str = "ch_sim+eng") -> str:
    # 兼容两种参数名
    if image_path and not path:
        path = image_path
    if not path:
        return "错误：请提供图片路径（参数名 path 或 image_path）"
    from core.path_policy import check_path
    path, err = check_path(path, must_exist=True, must_be_file=True)
    if err:
        return err
    if not os.path.isfile(path):
        return f"错误：文件不存在「{path}」"
    if not _is_supported_image(path):
        ext = os.path.splitext(path)[1]
        return f"错误：不支持的图片格式「{ext}」，支持 {', '.join(sorted(SUPPORTED_IMAGE_EXT))}"

    reader, engine_name = _get_ocr_engine()
    if reader is None:
        return (
            "错误：未安装 OCR 引擎。请安装以下之一：\n"
            "  1. easyocr（推荐）: pip install easyocr\n"
            "  2. pytesseract: pip install pytesseract（需额外安装 Tesseract-OCR 系统程序）"
        )

    try:
        if engine_name == "easyocr":
            text = _ocr_with_easyocr(reader, path, lang)
        elif engine_name == "tesseract":
            text = _ocr_with_tesseract(reader, path, lang)
        else:
            text = "未知 OCR 引擎"

        size = os.path.getsize(path)
        size_str = _format_size(size)
        return (
            f"📄 OCR 识别结果\n"
            f"文件: {os.path.basename(path)} ({size_str})\n"
            f"引擎: {engine_name} | 语言: {lang}\n"
            f"{'─' * 40}\n"
            f"{text}"
        )
    except Exception as e:
        return f"OCR 识别出错: {str(e)[:300]}"


# ═══════════════════════════════════════════════════════════════
# 工具：OCR 识别 PDF
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="ocr_pdf",
    description="对 PDF 文件进行 OCR 文字识别（将 PDF 页面转为图片后识别文字）",
    parameters={
        "path": {"type": "string", "description": "PDF 文件完整路径"},
        "image_path": {"type": "string", "description": "PDF 文件完整路径（path 的别名）"},
        "lang": {
            "type": "string",
            "description": "识别语言，默认 ch_sim+eng",
        },
        "pages": {
            "type": "string",
            "description": "要识别的页码范围，如 1-5 或 1,3,5，默认全部",
        },
    },
    category="utility",
    timeout=300,
)
def ocr_pdf(path: str = "", image_path: str = "", lang: str = "ch_sim+eng", pages: str = "") -> str:
    if image_path and not path:
        path = image_path
    if not path:
        return "错误：请提供 PDF 路径（参数名 path 或 image_path）"
    from core.path_policy import check_path
    path, err = check_path(path, must_exist=True, must_be_file=True)
    if err:
        return err
    if not os.path.isfile(path):
        return f"错误：文件不存在「{path}」"
    if os.path.splitext(path)[1].lower() != ".pdf":
        return "错误：仅支持 PDF 文件"

    reader, engine_name = _get_ocr_engine()
    if reader is None:
        return "错误：未安装 OCR 引擎（easyocr 或 pytesseract）"

    try:
        # 将 PDF 页面转为图片
        from pypdf import PdfReader
        pdf = PdfReader(path)

        total_pages = len(pdf.pages)
        page_range = _parse_page_range(pages, total_pages)

        results = []
        for page_num in page_range:
            # 使用 pdfplumber 或 pypdfium2 渲染页面为图片
            page_text = _ocr_pdf_page(path, page_num, reader, engine_name, lang)
            results.append(f"── 第 {page_num}/{total_pages} 页 ──\n{page_text}")

        summary = (
            f"📄 PDF OCR 识别完成\n"
            f"文件: {os.path.basename(path)} (共 {total_pages} 页)\n"
            f"引擎: {engine_name} | 识别: {len(page_range)} 页\n"
            f"{'═' * 40}\n"
        )
        return summary + "\n\n".join(results)

    except Exception as e:
        return f"PDF OCR 出错: {str(e)[:300]}"


def _parse_page_range(page_str: str, total: int) -> list[int]:
    """解析页码范围，返回 1-based 页码列表"""
    if not page_str:
        return list(range(1, total + 1))

    pages = set()
    for part in page_str.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            a, b = int(a.strip()), int(b.strip())
            pages.update(range(max(1, a), min(total, b) + 1))
        else:
            p = int(part)
            if 1 <= p <= total:
                pages.add(p)
    return sorted(pages) if pages else list(range(1, total + 1))


def _ocr_pdf_page(pdf_path: str, page_num: int, reader, engine_name: str, lang: str) -> str:
    """将 PDF 指定页转为图片后进行 OCR"""
    try:
        # 用 pypdfium2 渲染页面为高分辨率图片
        import pypdfium2 as pdfium
        pdf_doc = pdfium.PdfDocument(pdf_path)
        page = pdf_doc[page_num - 1]
        bitmap = page.render(scale=2)  # 2x 提高识别率
        pil_image = bitmap.to_pil()

        # 保存为临时文件
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = f.name
            pil_image.save(tmp_path, format="PNG")

        try:
            if engine_name == "easyocr":
                text = _ocr_with_easyocr(reader, tmp_path, lang)
            else:
                text = _ocr_with_tesseract(reader, tmp_path, lang)
            return text
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except ImportError:
        return "(需要 pypdfium2 库: pip install pypdfium2)"
    except Exception as e:
        return f"(第 {page_num} 页识别失败: {str(e)[:100]})"


# ═══════════════════════════════════════════════════════════════
# 工具：批量 OCR 识别
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="ocr_batch",
    description="批量识别文件夹中所有图片的文字（OCR），支持 PNG/JPG/BMP/TIFF",
    parameters={
        "directory": {"type": "string", "description": "要扫描的文件夹路径"},
        "lang": {
            "type": "string",
            "description": "识别语言，默认 ch_sim+eng",
        },
        "recursive": {
            "type": "boolean",
            "description": "是否递归扫描子文件夹，默认 false",
        },
    },
    category="utility",
    timeout=600,
)
def ocr_batch(directory: str, lang: str = "ch_sim+eng", recursive: bool = False) -> str:
    directory = os.path.abspath(directory)
    if not os.path.isdir(directory):
        return f"错误：文件夹不存在「{directory}」"

    reader, engine_name = _get_ocr_engine()
    if reader is None:
        return "错误：未安装 OCR 引擎（easyocr 或 pytesseract）"

    # 收集所有图片文件
    image_files = []
    if recursive:
        for root, dirs, files in os.walk(directory):
            for fn in files:
                if _is_supported_image(os.path.join(root, fn)):
                    image_files.append(os.path.join(root, fn))
    else:
        for fn in os.listdir(directory):
            full = os.path.join(directory, fn)
            if os.path.isfile(full) and _is_supported_image(full):
                image_files.append(full)

    if not image_files:
        supported = ", ".join(sorted(SUPPORTED_IMAGE_EXT))
        return f"在「{directory}」中未找到支持的图片文件（{supported}）"

    image_files.sort()
    results = []
    success = 0
    failed = 0

    for img_path in image_files:
        try:
            text = _ocr_with_easyocr(reader, img_path, lang) if engine_name == "easyocr" \
                else _ocr_with_tesseract(reader, img_path, lang)
            char_count = len(text.strip())
            results.append(f"  ✅ {os.path.basename(img_path)} ({char_count} 字符)")
            success += 1
        except Exception as e:
            results.append(f"  ❌ {os.path.basename(img_path)}: {str(e)[:60]}")
            failed += 1

    header = (
        f"📄 批量 OCR 识别结果\n"
        f"扫描目录: {directory}\n"
        f"引擎: {engine_name} | 语言: {lang}\n"
        f"总计: {len(image_files)} 文件 | 成功: {success} | 失败: {failed}\n"
        f"{'─' * 40}\n"
    )
    return header + "\n".join(results)


def _format_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"
