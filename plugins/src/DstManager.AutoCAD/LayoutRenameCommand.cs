using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;

namespace DstManager.AutoCAD
{
    internal static class LayoutRenameCommand
    {
        private const int SchemaVersion = 1;
        private static readonly char[] InvalidNameCharacters = { '<', '>', '/', '\\', '"', ':', ';', '?', '*', '|', '=' };

        public static void Execute(Document document)
        {
            if (document == null)
                throw new InvalidDataException("LAYOUT_RENAME_DOCUMENT_INVALID");

            Editor editor = document.Editor;
            Database database = document.Database;
            LayoutManager manager = LayoutManager.Current;
            string resultPath = null;
            var temporary = new List<TemporaryRename>();
            int firstPhaseCount = 0;
            int secondPhaseCount = 0;

            try
            {
                string expectedRequestPath = Path.GetFullPath(SidecarPath(database.Filename, ".dst-layout-rename-request.json"));
                resultPath = Path.GetFullPath(SidecarPath(database.Filename, ".dst-layout-rename-result.json"));
                string requestPath = Path.GetFullPath(ReadRequestPath(editor));
                if (!string.Equals(requestPath, expectedRequestPath, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("LAYOUT_RENAME_REQUEST_PATH_INVALID");

                DeleteResultIfPresent(resultPath);
                RenameRequest request = ReadRequest(requestPath);
                List<string> current = ReadPaperLayoutNames(database);
                ValidateRequest(request, current);

                foreach (RenameRow row in request.Layouts)
                {
                    if (!string.Equals(row.OldName, row.NewName, StringComparison.Ordinal))
                    {
                        temporary.Add(new TemporaryRename(
                            row.OldName,
                            row.NewName,
                            "DST_RENAME_" + Guid.NewGuid().ToString("N") + "_" + temporary.Count.ToString("D4")));
                    }
                }

                foreach (TemporaryRename item in temporary)
                {
                    manager.RenameLayout(item.OldName, item.TemporaryName);
                    firstPhaseCount++;
                }
                foreach (TemporaryRename item in temporary)
                {
                    manager.RenameLayout(item.TemporaryName, item.NewName);
                    secondPhaseCount++;
                }

                List<string> finalNames = ReadPaperLayoutNames(database);
                ValidateFinalNames(request, finalNames);
                WriteResult(resultPath, finalNames, temporary.Count);
                editor.WriteMessage("\nDST_MANAGER_LAYOUTS_RENAMED={0}", temporary.Count);
            }
            catch (Exception exception)
            {
                try
                {
                    RestoreOriginalNames(manager, temporary, firstPhaseCount, secondPhaseCount);
                }
                catch (Exception rollbackException)
                {
                    editor.WriteMessage("\nDST_MANAGER_LAYOUT_RENAME_ROLLBACK_FAILED={0}", rollbackException.Message);
                }
                if (resultPath != null)
                    DeleteResultIfPresent(resultPath);
                editor.WriteMessage("\nDST_MANAGER_LAYOUT_RENAME_FAILED={0}", exception.Message);
                throw;
            }
        }

        private static string ReadRequestPath(Editor editor)
        {
            PromptResult result = editor.GetString(new PromptStringOptions("\nDST 布局改名请求路径:") { AllowSpaces = true });
            if (result.Status != PromptStatus.OK || string.IsNullOrWhiteSpace(result.StringResult))
                throw new InvalidDataException("LAYOUT_RENAME_REQUEST_PATH_INVALID");
            return result.StringResult;
        }

        private static string SidecarPath(string drawingPath, string suffix)
        {
            if (string.IsNullOrWhiteSpace(drawingPath))
                throw new InvalidDataException("LAYOUT_RENAME_DRAWING_PATH_INVALID");
            return Path.Combine(Path.GetDirectoryName(drawingPath), Path.GetFileNameWithoutExtension(drawingPath) + suffix);
        }

        private static RenameRequest ReadRequest(string requestPath)
        {
            try
            {
                using (var stream = new FileStream(requestPath, FileMode.Open, FileAccess.Read, FileShare.Read))
                {
                    var serializer = new DataContractJsonSerializer(typeof(RenameRequest));
                    var request = serializer.ReadObject(stream) as RenameRequest;
                    if (request == null || stream.Position != stream.Length || request.ExtensionData != null)
                        throw new InvalidDataException("LAYOUT_RENAME_REQUEST_INVALID");
                    if (request.Layouts != null)
                    {
                        foreach (RenameRow row in request.Layouts)
                        {
                            if (row == null || row.ExtensionData != null)
                                throw new InvalidDataException("LAYOUT_RENAME_REQUEST_INVALID");
                        }
                    }
                    return request;
                }
            }
            catch (InvalidDataException)
            {
                throw;
            }
            catch (Exception exception) when (exception is IOException || exception is SerializationException || exception is ArgumentException)
            {
                throw new InvalidDataException("LAYOUT_RENAME_REQUEST_INVALID", exception);
            }
        }

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

        private static void ValidateRequest(RenameRequest request, List<string> current)
        {
            if (request.Version != SchemaVersion || request.Layouts == null || request.Layouts.Count == 0)
                throw new InvalidDataException("LAYOUT_RENAME_REQUEST_INVALID");

            var oldNames = new List<string>();
            var newNames = new List<string>();
            foreach (RenameRow row in request.Layouts)
            {
                ValidateLayoutName(row.OldName);
                ValidateLayoutName(row.NewName);
                oldNames.Add(row.OldName);
                newNames.Add(row.NewName);
            }

            EnsureUnique(oldNames);
            EnsureUnique(newNames);
            EnsureUnique(current);
            if (!SameNames(oldNames, current))
                throw new InvalidDataException("LAYOUT_RENAME_LAYOUT_SET_INVALID");
        }

        private static void ValidateFinalNames(RenameRequest request, List<string> finalNames)
        {
            var expected = new List<string>();
            foreach (RenameRow row in request.Layouts)
                expected.Add(row.NewName);
            EnsureUnique(finalNames);
            if (!SameNames(expected, finalNames))
                throw new InvalidDataException("LAYOUT_RENAME_FINAL_LAYOUT_SET_INVALID");
        }

        private static void ValidateLayoutName(string name)
        {
            if (string.IsNullOrWhiteSpace(name) || name.Length > 255 || string.Equals(name, "Model", StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("LAYOUT_RENAME_LAYOUT_NAME_INVALID");
            if (name.IndexOfAny(InvalidNameCharacters) >= 0)
                throw new InvalidDataException("LAYOUT_RENAME_LAYOUT_NAME_INVALID");
            foreach (char value in name)
            {
                if (char.IsControl(value))
                    throw new InvalidDataException("LAYOUT_RENAME_LAYOUT_NAME_INVALID");
            }
        }

        private static void EnsureUnique(IEnumerable<string> names)
        {
            var unique = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (string name in names)
            {
                if (!unique.Add(name))
                    throw new InvalidDataException("LAYOUT_RENAME_LAYOUT_SET_INVALID");
            }
        }

        private static bool SameNames(IEnumerable<string> first, IEnumerable<string> second)
        {
            var firstSet = new HashSet<string>(first, StringComparer.OrdinalIgnoreCase);
            var secondSet = new HashSet<string>(second, StringComparer.OrdinalIgnoreCase);
            return firstSet.Count == secondSet.Count && firstSet.SetEquals(secondSet);
        }

        private static void RestoreOriginalNames(LayoutManager manager, List<TemporaryRename> temporary, int firstPhaseCount, int secondPhaseCount)
        {
            for (int index = secondPhaseCount - 1; index >= 0; index--)
                manager.RenameLayout(temporary[index].NewName, temporary[index].TemporaryName);
            for (int index = firstPhaseCount - 1; index >= 0; index--)
                manager.RenameLayout(temporary[index].TemporaryName, temporary[index].OldName);
        }

        private static void WriteResult(string resultPath, List<string> finalNames, int renamedCount)
        {
            var result = new RenameResult
            {
                Version = SchemaVersion,
                RenamedCount = renamedCount,
                FinalLayouts = finalNames,
            };
            using (var stream = new FileStream(resultPath, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                var serializer = new DataContractJsonSerializer(typeof(RenameResult));
                serializer.WriteObject(stream, result);
            }
        }

        private static void DeleteResultIfPresent(string resultPath)
        {
            if (File.Exists(resultPath))
                File.Delete(resultPath);
        }

        private sealed class TemporaryRename
        {
            public TemporaryRename(string oldName, string newName, string temporaryName)
            {
                OldName = oldName;
                NewName = newName;
                TemporaryName = temporaryName;
            }

            public string OldName { get; private set; }
            public string NewName { get; private set; }
            public string TemporaryName { get; private set; }
        }
    }

    [DataContract]
    internal sealed class RenameRequest : IExtensibleDataObject
    {
        [DataMember(Name = "version", IsRequired = true)]
        public int Version { get; set; }

        [DataMember(Name = "layouts", IsRequired = true)]
        public List<RenameRow> Layouts { get; set; }

        public ExtensionDataObject ExtensionData { get; set; }
    }

    [DataContract]
    internal sealed class RenameRow : IExtensibleDataObject
    {
        [DataMember(Name = "old_name", IsRequired = true)]
        public string OldName { get; set; }

        [DataMember(Name = "new_name", IsRequired = true)]
        public string NewName { get; set; }

        public ExtensionDataObject ExtensionData { get; set; }
    }

    [DataContract]
    internal sealed class RenameResult
    {
        [DataMember(Name = "version", IsRequired = true)]
        public int Version { get; set; }

        [DataMember(Name = "renamed_count", IsRequired = true)]
        public int RenamedCount { get; set; }

        [DataMember(Name = "final_layouts", IsRequired = true)]
        public List<string> FinalLayouts { get; set; }
    }
}
