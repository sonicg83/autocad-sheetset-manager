using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Runtime;
using System;
using System.Collections.Generic;
using System.IO;

[assembly: CommandClass(typeof(DstBuilder.AutoCAD.Commands))]

namespace DstBuilder.AutoCAD
{
    /// <summary>
    /// Builder 唯一命令 DSTBUILDER_CREATE_DRAWING（SPEC-DB-001 §7）。
    /// 从 attempt 目录中的版本化 JSON 请求读取结构化数据：请求 Schema 为
    /// cad-drawing-request 时执行单 DWG 生成（导入布局 → 改名 → 清理 → 保存
    /// → 原子写出结果）；为 cad-inspect-request 时执行布局 inspection。
    /// 任何失败都不写出结果 JSON（Python 端以 CAD_EXECUTION_FAILED 阻断）。
    /// </summary>
    public sealed class Commands
    {
        [CommandMethod("DSTBUILDER_CREATE_DRAWING")]
        public void CreateDrawing()
        {
            Document document = Application.DocumentManager.MdiActiveDocument;
            Editor editor = document.Editor;

            PromptResult requestPathPrompt = editor.GetString("\nDSTBUILDER_REQUEST_JSON: ");
            if (requestPathPrompt.Status != PromptStatus.OK)
                return;
            string requestPath = requestPathPrompt.StringResult.Trim('"');

            try
            {
                string schema = CadDrawingContracts.ReadRequestSchema(requestPath);
                if (string.Equals(schema, CadDrawingSchemas.InspectRequest, StringComparison.Ordinal))
                    ExecuteInspect(document, editor, requestPath);
                else
                    ExecuteCreateDrawing(document, editor, requestPath);
            }
            catch (System.Exception exception)
            {
                editor.WriteMessage("\nDSTBUILDER_FAILED={0}", exception.Message);
            }
        }

        // ------------------------------------------------------------------
        // 单 DWG 生成
        // ------------------------------------------------------------------

        private static void ExecuteCreateDrawing(Document document, Editor editor, string requestPath)
        {
            Database database = document.Database;
            CadDrawingRequestV1 request = CadDrawingContracts.LoadDrawingRequest(requestPath);
            CadDrawingContracts.ValidateDrawingRequest(request, requestPath);

            List<string> currentPaperLayouts = ReadPaperLayoutNames(database);
            CadDrawingContracts.ValidateTargetLayoutAvailable(currentPaperLayouts, request.TargetLayout);

            LayoutManager manager = LayoutManager.Current;
            string importedName = ImportLayout(document, request);
            editor.WriteMessage("\nDSTBUILDER_IMPORT={0}", importedName);
            if (!string.Equals(importedName, request.TargetLayout, StringComparison.Ordinal))
                manager.RenameLayout(importedName, request.TargetLayout);

            // 只保留 Model 与目标布局：其余纸空间布局全部删除。
            DeletePaperLayoutsExcept(document, new List<string> { request.TargetLayout });

            List<string> final = ReadPaperLayoutNames(database);
            editor.WriteMessage("\nDSTBUILDER_FINAL={0}", string.Join(" | ", final));
            CadDrawingContracts.ValidateFinalPaperLayouts(final, request.TargetLayout);

            // §7 步骤 4：插件负责保存 DWG（SCR 末尾的 QSAVE 是双保险）。
            SaveDrawing(document, database);
            editor.WriteMessage("\nDSTBUILDER_SAVE=OK");

            string handle = GetLayoutHandle(database, request.TargetLayout);
            editor.WriteMessage("\nDSTBUILDER_HANDLE={0}", handle);
            CadDrawingContracts.ValidateLayoutHandle(handle);

            var result = new CadDrawingResultV1
            {
                Schema = CadDrawingSchemas.DrawingResult,
                RequestId = request.RequestId,
                LayoutName = request.TargetLayout,
                LayoutHandle = handle,
                DatabaseVersion = database.LastSavedAsVersion.ToString(),
                Layouts = final,
                Diagnostics = new List<CadDiagnostic>(),
            };
            CadDrawingContracts.WriteResultAtomically(request.ResultJson, CadDrawingContracts.SerializeResult(result));
            editor.WriteMessage("\nDSTBUILDER_OK={0}", request.TargetLayout);
        }

        private static string ImportLayout(Document document, CadDrawingRequestV1 request)
        {
            string assetPath = Path.GetFullPath(request.LayoutAssetPath);
            if (!File.Exists(assetPath))
                throw new InvalidDataException(CadDrawingErrorCodes.SourceLayoutMissing);

            Database database = document.Database;
            using (Database source = new Database(false, true))
            {
                source.ReadDwgFile(assetPath, FileOpenMode.OpenForReadAndAllShare, false, null);
                ObjectId sourceLayoutId;
                ObjectId sourcePaperBtrId;
                using (Transaction transaction = source.TransactionManager.StartTransaction())
                {
                    var layouts = (DBDictionary)transaction.GetObject(source.LayoutDictionaryId, OpenMode.ForRead);
                    if (!layouts.Contains(request.SourceLayout))
                        throw new InvalidDataException(CadDrawingErrorCodes.SourceLayoutMissing);
                    sourceLayoutId = layouts.GetAt(request.SourceLayout);
                    var sourceLayout = (Layout)transaction.GetObject(sourceLayoutId, OpenMode.ForRead);
                    sourcePaperBtrId = sourceLayout.BlockTableRecordId;
                    transaction.Abort();
                }

                // 直接克隆 Layout 对象会让源 DWG 的匿名纸空间块（*Paper_Space0）
                // 与工作副本同名冲突：Ignore 策略跳过克隆后两个布局共享同一块表记录，
                // AutoCAD 会再自动补出一个默认布局（如"布局1"），最终布局集合不合法。
                // 因此改为：先在目标库创建全新布局拿到独立纸空间块，再实体级克隆内容，
                // 最后用 CopyFrom 复制源布局的打印设置。
                LayoutManager manager = LayoutManager.Current;
                ObjectId targetLayoutId = manager.CreateLayout(request.TargetLayout);
                ObjectId targetPaperBtrId;
                using (Transaction transaction = database.TransactionManager.StartTransaction())
                {
                    var targetLayout = (Layout)transaction.GetObject(targetLayoutId, OpenMode.ForWrite);
                    targetPaperBtrId = targetLayout.BlockTableRecordId;
                    transaction.Abort();
                }

                var entityIds = new Autodesk.AutoCAD.DatabaseServices.ObjectIdCollection();
                using (Transaction transaction = source.TransactionManager.StartTransaction())
                {
                    var paperBtr = (BlockTableRecord)transaction.GetObject(sourcePaperBtrId, OpenMode.ForRead);
                    foreach (ObjectId entityId in paperBtr)
                        entityIds.Add(entityId);
                    transaction.Abort();
                }

                if (entityIds.Count > 0)
                {
                    var mapping = new IdMapping();
                    mapping.DestinationDatabase = database;
                    source.WblockCloneObjects(entityIds, targetPaperBtrId, mapping, DuplicateRecordCloning.Ignore, false);
                }

                using (Transaction sourceTransaction = source.TransactionManager.StartTransaction())
                {
                    var sourceLayout = (Layout)sourceTransaction.GetObject(sourceLayoutId, OpenMode.ForRead);
                    using (Transaction transaction = database.TransactionManager.StartTransaction())
                    {
                        var targetLayout = (Layout)transaction.GetObject(targetLayoutId, OpenMode.ForWrite);
                        targetLayout.CopyFrom(sourceLayout);
                        transaction.Commit();
                    }
                    sourceTransaction.Abort();
                }
            }
            return request.TargetLayout;
        }

        // ------------------------------------------------------------------
        // 布局 inspection
        // ------------------------------------------------------------------

        private static void ExecuteInspect(Document document, Editor editor, string requestPath)
        {
            Database database = document.Database;
            CadInspectRequestV1 request = CadDrawingContracts.LoadInspectRequest(requestPath);
            CadDrawingContracts.EnsureUnderDirectory(
                request.ResultJson, Path.GetDirectoryName(Path.GetFullPath(database.Filename)));

            var result = new CadInspectResultV1
            {
                Schema = CadDrawingSchemas.InspectResult,
                RequestId = request.RequestId,
                Layouts = ReadPaperLayoutNames(database),
            };
            CadDrawingContracts.WriteResultAtomically(request.ResultJson, CadDrawingContracts.SerializeResult(result));
            editor.WriteMessage("\nDSTBUILDER_INSPECT_OK={0}", result.Layouts.Count);
        }

        // ------------------------------------------------------------------
        // 数据库辅助
        // ------------------------------------------------------------------

        private static List<string> ReadPaperLayoutNames(Database database)
        {
            var names = new List<string>();
            using (Transaction transaction = database.TransactionManager.StartTransaction())
            {
                var layouts = (DBDictionary)transaction.GetObject(database.LayoutDictionaryId, OpenMode.ForRead);
                foreach (DBDictionaryEntry entry in layouts)
                {
                    if (!string.Equals(entry.Key, "Model", StringComparison.OrdinalIgnoreCase))
                        names.Add(entry.Key);
                }
                transaction.Abort();
            }
            names.Sort(StringComparer.Ordinal);
            return names;
        }

        private static void DeletePaperLayoutsExcept(Document document, List<string> keep)
        {
            Database database = document.Database;
            LayoutManager manager = LayoutManager.Current;
            manager.CurrentLayout = "Model";
            var deletable = new List<string>();
            using (Transaction transaction = database.TransactionManager.StartTransaction())
            {
                var layouts = (DBDictionary)transaction.GetObject(database.LayoutDictionaryId, OpenMode.ForRead);
                foreach (DBDictionaryEntry entry in layouts)
                {
                    if (string.Equals(entry.Key, "Model", StringComparison.OrdinalIgnoreCase))
                        continue;
                    bool preserved = false;
                    foreach (string name in keep)
                    {
                        if (string.Equals(entry.Key, name, StringComparison.OrdinalIgnoreCase))
                        {
                            preserved = true;
                            break;
                        }
                    }
                    if (!preserved)
                        deletable.Add(entry.Key);
                }
                transaction.Abort();
            }
            foreach (string name in deletable)
                manager.DeleteLayout(name);
        }

        private static string GetLayoutHandle(Database database, string layoutName)
        {
            using (Transaction transaction = database.TransactionManager.StartTransaction())
            {
                var layouts = (DBDictionary)transaction.GetObject(database.LayoutDictionaryId, OpenMode.ForRead);
                string handle = layouts.GetAt(layoutName).Handle.ToString().ToUpperInvariant();
                transaction.Abort();
                return handle;
            }
        }

        private static void SaveDrawing(Document document, Database database)
        {
            // Core Console 下 Database.SaveAs 不允许覆盖当前文档已打开的原路径
            // （抛 eInvalidInput），因此保存到 attempt 目录内的固定派生名
            // ``working.saved.dwg``；进程退出、句柄释放后由 Python 侧收敛回
            // ``working.dwg``（见 CoreConsoleDrawingBuilder.build）。
            string savedPath = Path.ChangeExtension(database.Filename, ".saved.dwg");
            database.SaveAs(savedPath, false, DwgVersion.Current, database.SecurityParameters);
        }
    }
}
