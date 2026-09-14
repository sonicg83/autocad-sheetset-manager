"""发布事务异常（自 publisher.py 拆分；错误码与继承关系逐字保留）。"""


class PublishRolledBackError(RuntimeError):
    code = "PUBLISH_ROLLED_BACK"


class PublishRecoveryError(RuntimeError):
    code = "PUBLISH_RECOVERY_FAILED"


class PublishOperationConflictError(PublishRecoveryError):
    """同一发布操作的修订目录无法安全复用（已提交修订或同号 attempt 现场未恢复）。

    每次发布尝试独占 ``revisions/<job_id>/attempt-NNN/`` 目录：任务重试由数据库
    attempt 计数严格递增，永远落在新目录上，因此不存在「回收上一次尝试」问题；
    上一次尝试的目录永久保留，不由发布路径自动删除。``journal["operation_id"]``
    保持等于 job_id，是启动恢复与提交后闭环查库的键；``journal["attempt"]``
    用于按路径重建修订目录。继承 ``PublishRecoveryError`` 以沿用「隔离而不是
    循环重试」的既有处置。
    """

    code = "PUBLISH_OPERATION_CONFLICT"


class PublishBaselineError(RuntimeError):
    code = "PUBLISH_BASE_CHANGED"


class PublishJournalWriteError(OSError):
    """发布日志在限定重试后仍写入失败（外部文件过滤驱动占用或真实写盘故障）。

    继承 ``OSError`` 以保持发布器「日志写失败即普通发布故障」的既有语义；该异常最终
    由通用失败分支包装成 ``PublishRolledBackError``，其消息直接成为任务 ``error_detail``，
    因此这里必须给出人能看懂的原因而不是裸 WinError。
    """

    code = "PUBLISH_JOURNAL_WRITE_FAILED"
