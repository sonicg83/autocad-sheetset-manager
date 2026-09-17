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

            // 同名冲突会让 WblockClone 的 Ignore 策略跳过克隆：先把占名者让开。
            LayoutManager manager = LayoutManager.Current;
            foreach (string name in currentPaperLayouts)
            {
                if (string.Equals(name, request.SourceLayout, StringComparison.OrdinalIgnoreCase))
                    manager.RenameLayout(name, "DSTB_TMP_" + Guid.NewGuid().ToString("N"));
            }

            string importedName = ImportLayout(document, request);
            if (!string.Equals(importedName, request.TargetLayout, StringComparison.Ordinal))
                manager.RenameLayout(importedName, request.TargetLayout);

            // 只保留 Model 与目标布局：其余纸空间布局全部删除。
            DeletePaperLayoutsExcept(document, new List<string> { request.TargetLayout });

            List<string> final = ReadPaperLayoutNames(database);
            CadDrawingContracts.ValidateFinalPaperLayouts(final, request.TargetLayout);
            manager.CurrentLayout = request.TargetLayout;

            // §7 步骤 4：插件负责保存 DWG（SCR 末尾的 QSAVE 是双保险）。
            SaveDrawing(document, database);

            string handle = GetLayoutHandle(database, request.TargetLayout);
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
            string importedName;
            using (Database source = new Database(false, true))
            {
                source.ReadDwgFile(assetPath, FileOpenMode.OpenForReadAndAllShare, false, null);
                var sourceLayoutIds = new Autodesk.AutoCAD.DatabaseServices.ObjectIdCollection();
                using (Transaction transaction = source.TransactionManager.StartTransaction())
                {
                    var layouts = (DBDictionary)transaction.GetObject(source.LayoutDictionaryId, OpenMode.ForRead);
                    if (!layouts.Contains(request.SourceLayout))
                        throw new InvalidDataException(CadDrawingErrorCodes.SourceLayoutMissing);
                    sourceLayoutIds.Add(layouts.GetAt(request.SourceLayout));
                    transaction.Commit();
                }

                var mapping = new IdMapping();
                mapping.DestinationDatabase = database;
                source.WblockCloneObjects(sourceLayoutIds, database.LayoutDictionaryId, mapping, DuplicateRecordCloning.Ignore, false);

                using (Transaction transaction = database.TransactionManager.StartTransaction())
                {
                    var cloned = (Layout)transaction.GetObject(mapping.Lookup(sourceLayoutIds[0]).Value, OpenMode.ForRead);
                    importedName = cloned.LayoutName;
                    transaction.Abort();
                }
            }
            return importedName;
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
            database.SaveAs(database.Filename, true, database.LastSavedAsVersion, database.SecurityParameters);
        }
    }
}
