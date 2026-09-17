"""运行日志文本协议（PLAN-DB-001 Task 6：``sanitize_log_text`` 实现所有权已迁至
``dst_platform.autocad.process``，此处仅薄 re-export；``validate_log_bytes`` 为
Manager 日志文件通道的本地协议校验，仍归 Manager 所有）。
"""

from dst_platform.autocad.process import sanitize_log_text

__all__ = ["sanitize_log_text", "validate_log_bytes"]

_ALLOWED_CONTROLS = {"\t", "\n", "\r"}


def validate_log_bytes(data: bytes) -> None:
    """严格验证运行日志编码和控制字符协议。"""
    text = data.decode("utf-8", errors="strict")
    invalid = [character for character in text if (ord(character) < 32 and character not in _ALLOWED_CONTROLS) or ord(character) == 127]
    if invalid:
        raise ValueError(f"LOG_CONTROL_CHARACTER_INVALID: U+{ord(invalid[0]):04X}")
