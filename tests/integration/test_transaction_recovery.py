from dst_manager.application.service import DstManagerService
from dst_manager.config import Settings
from dst_manager.infrastructure.filesystem.publisher import RecoverablePublisher


def test_archive_failure_enters_needs_review_then_startup_finalizes_after_manifest_recovers(
    tmp_path,
    tiny_workspace,
    monkeypatch,
):
    dst, _ = tiny_workspace
    settings = Settings(data_dir=tmp_path / "data")
    service = DstManagerService(settings)
    workspace = service.open_workspace(dst)

    def fail_archive_once(*_args):
        raise OSError("注入首次 manifest 归档失败")

    monkeypatch.setattr(service.publisher, "_archive_journal", fail_archive_once)

    result = service.execute_changes(
        workspace.id,
        workspace.revision_id,
        [{"type": "update_sheet_set", "name": "等待归档恢复"}],
    )

    assert result["status"] == "NEEDS_REVIEW"
    assert result["error_code"] == "COMMITTED_FINALIZE_MISSING"
    assert service.database.list_revisions(workspace.id) == []
    with service.database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM workspace_write_locks").scalar_one() == 0

    restarted = DstManagerService(settings)

    assert restarted.database.get_job(result["id"])["status"] == "SUCCEEDED"
    assert len(restarted.database.list_revisions(workspace.id)) == 1


def test_persistent_archive_failure_never_finalizes_without_manifest_and_later_recovers(
    tmp_path,
    tiny_workspace,
    monkeypatch,
):
    dst, _ = tiny_workspace
    settings = Settings(data_dir=tmp_path / "data")
    service = DstManagerService(settings)
    workspace = service.open_workspace(dst)
    original_archive = RecoverablePublisher._archive_journal

    def fail_archive(*_args):
        raise OSError("注入持续 manifest 归档失败")

    monkeypatch.setattr(RecoverablePublisher, "_archive_journal", staticmethod(fail_archive))
    result = service.execute_changes(
        workspace.id,
        workspace.revision_id,
        [{"type": "update_sheet_set", "name": "持续等待归档"}],
    )

    failed_restart = DstManagerService(settings)

    assert result["status"] == "NEEDS_REVIEW"
    assert failed_restart.database.get_job(result["id"])["status"] == "NEEDS_REVIEW"
    assert failed_restart.database.list_revisions(workspace.id) == []
    with failed_restart.database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM workspace_write_locks").scalar_one() == 0

    monkeypatch.setattr(
        RecoverablePublisher,
        "_archive_journal",
        staticmethod(original_archive),
    )
    recovered_restart = DstManagerService(settings)

    assert recovered_restart.database.get_job(result["id"])["status"] == "SUCCEEDED"
    assert len(recovered_restart.database.list_revisions(workspace.id)) == 1
