"""应用层公共异常（v0.3.2 Task 0 自 service.py 拆分）。

`ApplicationError` 是编排入口与全部功能域模块共享的异常类型；拆分后
放于独立模块以规避 service.py 与功能域模块间的循环导入。service.py
继续以 `from dst_manager.application.errors import ApplicationError`
导入并对外保持 `dst_manager.application.service.ApplicationError` 可访问。
"""


class ApplicationError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        params: dict[str, object] | None = None,
    ):
        super().__init__(message)
        self.code, self.status_code = code, status_code
        # PLAN-DM-021 Task 9：可选结构化插值参数（仅稳定值：路径/标识/编号等，
        # 禁止本地化 label 或完整句子）；由接口层错误目录按 code 的参数 schema
        # 校验后写入统一错误负载，未提供时由接口层从详情规则提取。
        self.params = dict(params) if params else None
