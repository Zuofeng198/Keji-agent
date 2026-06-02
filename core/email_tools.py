"""邮件处理工具 —— 解析 .eml / .msg 邮件文件，提取正文和附件"""

import os
import email
import re
from email import policy
from email.utils import parsedate_to_datetime
from typing import Optional

from core.tools import register_tool


def _format_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def _decode_header_value(value) -> str:
    """解码邮件头字段（处理 =?UTF-8?B? 等编码）"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        decoded = email.header.decode_header(value)
        parts = []
        for part, charset in decoded:
            if isinstance(part, bytes):
                try:
                    parts.append(part.decode(charset or "utf-8", errors="replace"))
                except (LookupError, UnicodeDecodeError):
                    parts.append(part.decode("utf-8", errors="replace"))
            else:
                parts.append(str(part))
        return " ".join(parts)
    except Exception:
        return str(value)


def _parse_email_address(address_str: str) -> str:
    """解析邮件地址字段为可读格式"""
    if not address_str:
        return ""
    try:
        addrs = email.utils.getaddresses([address_str])
        return "; ".join(f"{name} <{addr}>" if name else addr for name, addr in addrs)
    except Exception:
        return address_str


# ═══════════════════════════════════════════════════════════════
# 工具：解析邮件文件
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="parse_email",
    description="解析邮件文件（支持 .eml 和 .msg 格式），获取发件人、收件人、主题、正文、附件列表",
    parameters={
        "path": {"type": "string", "description": "邮件文件完整路径（.eml 或 .msg）"},
        "extract_body": {
            "type": "boolean",
            "description": "是否提取邮件正文，默认 true",
        },
        "max_body_length": {
            "type": "integer",
            "description": "正文最大字符数，默认 3000",
        },
    },
    category="utility",
    timeout=30,
)
def parse_email(path: str, extract_body: bool = True, max_body_length: int = 3000) -> str:
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return f"错误：文件不存在「{path}」"

    ext = os.path.splitext(path)[1].lower()
    if ext == ".eml":
        return _parse_eml(path, extract_body, max_body_length)
    elif ext == ".msg":
        return _parse_msg(path, extract_body, max_body_length)
    else:
        return "错误：仅支持 .eml 和 .msg 格式的邮件文件"


def _parse_eml(path: str, extract_body: bool, max_body_length: int) -> str:
    try:
        with open(path, "rb") as f:
            msg = email.message_from_binary_file(f, policy=policy.default)
    except Exception as e:
        return f"读取邮件失败: {str(e)[:200]}"

    # 基本信息
    subject = _decode_header_value(msg.get("Subject", ""))
    sender = _parse_email_address(str(msg.get("From", "")))
    to = _parse_email_address(str(msg.get("To", "")))
    cc = _parse_email_address(str(msg.get("Cc", "")))
    date = msg.get("Date", "")

    # 解析日期
    date_str = date
    try:
        dt = parsedate_to_datetime(date)
        if dt:
            date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    lines = [
        f"📧 邮件解析结果",
        f"{'═' * 40}",
        f"主题: {subject or '(无主题)'}",
        f"发件人: {sender or '(未知)'}",
        f"收件人: {to or '(未知)'}",
    ]
    if cc:
        lines.append(f"抄送: {cc}")
    lines.append(f"日期: {date_str}")

    # 附件列表
    attachments = []
    body_text = ""
    body_html = ""

    for part in msg.walk():
        content_disposition = str(part.get("Content-Disposition", ""))
        content_type = part.get_content_type()

        # 附件
        if "attachment" in content_disposition.lower():
            filename = part.get_filename()
            if filename:
                filename = _decode_header_value(filename)
                size = len(part.get_payload(decode=True) or b"")
                attachments.append(f"{filename} ({_format_size(size)})")

        # 正文（优先取 plain 文本）
        if extract_body and part.get_content_type() == "text/plain":
            try:
                payload = part.get_content()
                if payload:
                    body_text = payload
            except Exception:
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body_text = payload.decode("utf-8", errors="replace")
                except Exception:
                    pass

        if extract_body and part.get_content_type() == "text/html" and not body_text:
            try:
                payload = part.get_content()
                if payload:
                    body_html = payload
            except Exception:
                pass

    if attachments:
        lines.append(f"\n📎 附件 ({len(attachments)} 个):")
        for a in attachments:
            lines.append(f"  - {a}")
    else:
        lines.append("\n📎 附件: 无")

    # 正文
    if extract_body:
        body = body_text or body_html
        if body:
            # 简单清理 HTML
            if body_html and not body_text:
                body = re.sub(r"<[^>]+>", "", body_html)
                body = re.sub(r"\s+", " ", body).strip()

            if len(body) > max_body_length:
                body = body[:max_body_length] + f"\n\n...（正文过长，仅显示前 {max_body_length} 字符）"
            lines.append(f"\n{'─' * 40}\n📝 正文:\n{body}")
        else:
            lines.append(f"\n{'─' * 40}\n📝 正文: (无正文内容)")

    return "\n".join(lines)


def _parse_msg(path: str, extract_body: bool, max_body_length: int) -> str:
    """解析 .msg 格式邮件（Outlook）"""
    try:
        import extract_msg
    except ImportError:
        return (
            "错误：请先安装 extract-msg 库以支持 .msg 格式：\n"
            "  pip install extract-msg"
        )

    try:
        msg = extract_msg.Message(path)
        msg.getMessage()  # 解析完整内容

        lines = [
            f"📧 邮件解析结果 (.msg)",
            f"{'═' * 40}",
            f"主题: {msg.subject or '(无主题)'}",
            f"发件人: {msg.sender or '(未知)'}",
            f"收件人: {msg.to or '(未知)'}",
        ]
        if msg.cc:
            lines.append(f"抄送: {msg.cc}")
        if msg.date:
            lines.append(f"日期: {msg.date}")

        # 附件
        attachments = []
        for att in msg.attachments:
            attachments.append(f"{att.longFilename or att.shortFilename} ({_format_size(att.dataSize)})" if hasattr(att, 'dataSize') else f"{att.longFilename or att.shortFilename}")

        if attachments:
            lines.append(f"\n📎 附件 ({len(attachments)} 个):")
            for a in attachments:
                lines.append(f"  - {a}")
        else:
            lines.append("\n📎 附件: 无")

        # 正文
        if extract_body:
            body = msg.body or msg.getHtmlBody() or ""
            if body:
                # HTML 清理
                if msg.getHtmlBody() and not msg.body:
                    body = re.sub(r"<[^>]+>", "", body)
                    body = re.sub(r"\s+", " ", body).strip()

                if len(body) > max_body_length:
                    body = body[:max_body_length] + f"\n\n...（正文过长，仅显示前 {max_body_length} 字符）"
                lines.append(f"\n{'─' * 40}\n📝 正文:\n{body}")
            else:
                lines.append(f"\n{'─' * 40}\n📝 正文: (无正文内容)")

        return "\n".join(lines)

    except Exception as e:
        return f"解析 .msg 文件失败: {str(e)[:300]}"


# ═══════════════════════════════════════════════════════════════
# 工具：提取邮件附件
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="extract_email_attachments",
    description="提取邮件文件中的所有附件到指定目录",
    parameters={
        "path": {"type": "string", "description": "邮件文件完整路径（.eml 或 .msg）"},
        "output_dir": {
            "type": "string",
            "description": "附件保存目录，默认保存到邮件所在目录的「附件」子文件夹",
        },
    },
    category="utility",
    timeout=60,
)
def extract_email_attachments(path: str, output_dir: str = "") -> str:
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return f"错误：文件不存在「{path}」"

    ext = os.path.splitext(path)[1].lower()
    if ext == ".eml":
        return _extract_eml_attachments(path, output_dir)
    elif ext == ".msg":
        return _extract_msg_attachments(path, output_dir)
    else:
        return "错误：仅支持 .eml 和 .msg 格式"


def _extract_eml_attachments(path: str, output_dir: str) -> str:
    try:
        with open(path, "rb") as f:
            msg = email.message_from_binary_file(f, policy=policy.default)
    except Exception as e:
        return f"读取邮件失败: {str(e)[:200]}"

    if not output_dir:
        base_dir = os.path.dirname(path)
        output_dir = os.path.join(base_dir, "附件")
    os.makedirs(output_dir, exist_ok=True)

    saved = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = part.get_filename()
        if not filename:
            continue
        filename = _decode_header_value(filename)
        if not filename:
            continue

        payload = part.get_payload(decode=True)
        if payload is None:
            continue

        # 避免路径穿越
        safe_name = os.path.basename(filename)
        target = os.path.join(output_dir, safe_name)

        # 重名处理
        if os.path.exists(target):
            base, ext = os.path.splitext(safe_name)
            counter = 1
            while os.path.exists(os.path.join(output_dir, f"{base}_{counter}{ext}")):
                counter += 1
            target = os.path.join(output_dir, f"{base}_{counter}{ext}")

        try:
            with open(target, "wb") as f:
                f.write(payload)
            saved.append(f"  ✅ {safe_name} ({_format_size(len(payload))})")
        except Exception as e:
            saved.append(f"  ❌ {safe_name}: {str(e)[:60]}")

    if not saved:
        return "未找到附件"

    return (
        f"📎 附件提取完成\n"
        f"来源: {os.path.basename(path)}\n"
        f"保存到: {output_dir}\n"
        f"共 {len(saved)} 个附件:\n" + "\n".join(saved)
    )


def _extract_msg_attachments(path: str, output_dir: str) -> str:
    try:
        import extract_msg
    except ImportError:
        return "错误：请先安装 extract-msg 库（pip install extract-msg）"

    try:
        msg = extract_msg.Message(path)
        msg.getMessage()

        if not output_dir:
            base_dir = os.path.dirname(path)
            output_dir = os.path.join(base_dir, "附件")
        os.makedirs(output_dir, exist_ok=True)

        saved = []
        for att in msg.attachments:
            filename = att.longFilename or att.shortFilename
            if not filename:
                continue

            safe_name = os.path.basename(filename)
            target = os.path.join(output_dir, safe_name)

            if os.path.exists(target):
                base, ext = os.path.splitext(safe_name)
                counter = 1
                while os.path.exists(os.path.join(output_dir, f"{base}_{counter}{ext}")):
                    counter += 1
                target = os.path.join(output_dir, f"{base}_{counter}{ext}")

            try:
                data = att.data
                with open(target, "wb") as f:
                    f.write(data)
                saved.append(f"  ✅ {safe_name} ({_format_size(len(data))})")
            except Exception as e:
                saved.append(f"  ❌ {safe_name}: {str(e)[:60]}")

        if not saved:
            return "未找到附件"
        return (
            f"📎 附件提取完成\n"
            f"来源: {os.path.basename(path)}\n"
            f"保存到: {output_dir}\n"
            f"共 {len(saved)} 个附件:\n" + "\n".join(saved)
        )
    except Exception as e:
        return f"提取 .msg 附件失败: {str(e)[:300]}"


# ═══════════════════════════════════════════════════════════════
# 工具：批量解析邮件
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="batch_parse_emails",
    description="批量解析文件夹中所有 .eml/.msg 邮件文件",
    parameters={
        "directory": {"type": "string", "description": "包含邮件文件的文件夹路径"},
        "recursive": {
            "type": "boolean",
            "description": "是否递归扫描子文件夹，默认 false",
        },
    },
    category="utility",
    timeout=120,
)
def batch_parse_emails(directory: str, recursive: bool = False) -> str:
    directory = os.path.abspath(directory)
    if not os.path.isdir(directory):
        return f"错误：文件夹不存在「{directory}」"

    # 收集邮件文件
    email_files = []
    if recursive:
        for root, dirs, files in os.walk(directory):
            for fn in files:
                if fn.lower().endswith((".eml", ".msg")):
                    email_files.append(os.path.join(root, fn))
    else:
        for fn in os.listdir(directory):
            full = os.path.join(directory, fn)
            if os.path.isfile(full) and fn.lower().endswith((".eml", ".msg")):
                email_files.append(full)

    if not email_files:
        return f"在「{directory}」中未找到邮件文件（.eml / .msg）"

    email_files.sort()
    results = []
    success = 0
    failed = 0

    for ef in email_files:
        try:
            result = parse_email(ef, extract_body=False)
            # 提取关键信息
            lines = result.split("\n")
            subject = ""
            sender = ""
            date = ""
            attachments = 0
            for line in lines:
                if line.startswith("主题:"):
                    subject = line[3:].strip()
                elif line.startswith("发件人:"):
                    sender = line[4:].strip()
                elif line.startswith("日期:"):
                    date = line[3:].strip()
                elif "附件" in line and "个)" in line:
                    import re
                    m = re.search(r"(\d+)", line)
                    if m:
                        attachments = int(m.group(1))

            results.append(
                f"  ✅ {os.path.basename(ef)}\n"
                f"     主题: {subject[:50]}\n"
                f"     发件人: {sender[:30]} | 日期: {date[:16]} | 附件: {attachments}"
            )
            success += 1
        except Exception as e:
            results.append(f"  ❌ {os.path.basename(ef)}: {str(e)[:60]}")
            failed += 1

    header = (
        f"📧 批量邮件解析结果\n"
        f"扫描目录: {directory}\n"
        f"总计: {len(email_files)} 封 | 成功: {success} | 失败: {failed}\n"
        f"{'═' * 40}\n"
    )
    return header + "\n\n".join(results)
