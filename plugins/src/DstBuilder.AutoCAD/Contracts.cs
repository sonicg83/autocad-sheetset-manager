using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;

namespace DstBuilder.AutoCAD
{
    /// <summary>版本化契约 Schema（SPEC-DB-001 §7）。未知 Schema 一律阻断。</summary>
    public static class CadDrawingSchemas
    {
        public const string DrawingRequest = "dst-builder.cad-drawing-request/v1";
        public const string DrawingResult = "dst-builder.cad-drawing-result/v1";
        public const string InspectRequest = "dst-builder.cad-inspect-request/v1";
        public const string InspectResult = "dst-builder.cad-inspect-result/v1";
    }

    /// <summary>插件侧契约错误码（Python 端统一以 CAD_EXECUTION_FAILED 阻断 attempt）。</summary>
    public static class CadDrawingErrorCodes
    {
        public const string SchemaUnknown = "DSTBUILDER_SCHEMA_UNKNOWN";
        public const string RequestInvalid = "DSTBUILDER_REQUEST_INVALID";
        public const string PathEscape = "DSTBUILDER_PATH_ESCAPE";
        public const string BaseDwgMissing = "DSTBUILDER_BASE_DWG_MISSING";
        public const string LayoutNameInvalid = "DSTBUILDER_LAYOUT_NAME_INVALID";
        public const string SourceLayoutMissing = "DSTBUILDER_SOURCE_LAYOUT_MISSING";
        public const string TargetLayoutConflict = "DSTBUILDER_TARGET_LAYOUT_CONFLICT";
        public const string FinalLayoutSetInvalid = "DSTBUILDER_FINAL_LAYOUT_SET_INVALID";
        public const string HandleInvalid = "DSTBUILDER_HANDLE_INVALID";
        public const string ImportFailed = "DSTBUILDER_LAYOUT_IMPORT_FAILED";
    }

    [DataContract]
    public sealed class CadDrawingRequestV1 : IExtensibleDataObject
    {
        [DataMember(Name = "schema", IsRequired = true)]
        public string Schema { get; set; }

        [DataMember(Name = "request_id", IsRequired = true)]
        public string RequestId { get; set; }

        [DataMember(Name = "base_dwg", IsRequired = true)]
        public string BaseDwg { get; set; }

        [DataMember(Name = "layout_asset", IsRequired = true)]
        public string LayoutAsset { get; set; }

        [DataMember(Name = "layout_asset_path", IsRequired = true)]
        public string LayoutAssetPath { get; set; }

        [DataMember(Name = "source_layout", IsRequired = true)]
        public string SourceLayout { get; set; }

        [DataMember(Name = "target_layout", IsRequired = true)]
        public string TargetLayout { get; set; }

        [DataMember(Name = "result_json", IsRequired = true)]
        public string ResultJson { get; set; }

        public ExtensionDataObject ExtensionData { get; set; }
    }

    [DataContract]
    public sealed class CadInspectRequestV1 : IExtensibleDataObject
    {
        [DataMember(Name = "schema", IsRequired = true)]
        public string Schema { get; set; }

        [DataMember(Name = "request_id", IsRequired = true)]
        public string RequestId { get; set; }

        [DataMember(Name = "result_json", IsRequired = true)]
        public string ResultJson { get; set; }

        public ExtensionDataObject ExtensionData { get; set; }
    }

    [DataContract]
    public sealed class CadDrawingResultV1
    {
        [DataMember(Name = "schema", IsRequired = true)]
        public string Schema { get; set; }

        [DataMember(Name = "request_id", IsRequired = true)]
        public string RequestId { get; set; }

        [DataMember(Name = "layout_name", IsRequired = true)]
        public string LayoutName { get; set; }

        [DataMember(Name = "layout_handle", IsRequired = true)]
        public string LayoutHandle { get; set; }

        [DataMember(Name = "database_version", IsRequired = true)]
        public string DatabaseVersion { get; set; }

        [DataMember(Name = "layouts", IsRequired = true)]
        public List<string> Layouts { get; set; }

        [DataMember(Name = "diagnostics", IsRequired = true)]
        public List<CadDiagnostic> Diagnostics { get; set; }
    }

    [DataContract]
    public sealed class CadInspectResultV1
    {
        [DataMember(Name = "schema", IsRequired = true)]
        public string Schema { get; set; }

        [DataMember(Name = "request_id", IsRequired = true)]
        public string RequestId { get; set; }

        [DataMember(Name = "layouts", IsRequired = true)]
        public List<string> Layouts { get; set; }
    }

    [DataContract]
    public sealed class CadDiagnostic
    {
        [DataMember(Name = "code", IsRequired = true)]
        public string Code { get; set; }

        [DataMember(Name = "severity", IsRequired = true)]
        public string Severity { get; set; }

        [DataMember(Name = "message", IsRequired = true)]
        public string Message { get; set; }
    }

    /// <summary>
    /// 纯契约载入/校验/序列化/原子写出。不依赖任何 AutoCAD 程序集：
    /// 测试项目直接链接本文件（PLAN-DB-001 Task 7）。
    /// </summary>
    public static class CadDrawingContracts
    {
        private static readonly char[] InvalidNameCharacters = { '<', '>', '/', '\\', '"', ':', ';', '?', '*', '|', '=' };
        private static readonly FieldInfo ExtensionDataMembersField = typeof(ExtensionDataObject).GetField(
            "members", BindingFlags.Instance | BindingFlags.NonPublic);

        // ------------------------------------------------------------------
        // 载入（严格 JSON：未知字段一律拒绝）
        // ------------------------------------------------------------------

        public static string ReadRequestSchema(string requestPath)
        {
            var probe = Deserialize<SchemaProbe>(requestPath);
            if (probe == null || string.IsNullOrEmpty(probe.Schema))
                throw new InvalidDataException(CadDrawingErrorCodes.RequestInvalid);
            return probe.Schema;
        }

        public static CadDrawingRequestV1 LoadDrawingRequest(string requestPath)
        {
            CadDrawingRequestV1 request = Deserialize<CadDrawingRequestV1>(requestPath);
            if (request == null || !string.Equals(request.Schema, CadDrawingSchemas.DrawingRequest, StringComparison.Ordinal))
                throw new InvalidDataException(CadDrawingErrorCodes.SchemaUnknown);
            if (string.IsNullOrEmpty(request.RequestId) || string.IsNullOrEmpty(request.BaseDwg)
                || string.IsNullOrEmpty(request.LayoutAsset) || string.IsNullOrEmpty(request.LayoutAssetPath)
                || string.IsNullOrEmpty(request.SourceLayout) || string.IsNullOrEmpty(request.TargetLayout)
                || string.IsNullOrEmpty(request.ResultJson))
                throw new InvalidDataException(CadDrawingErrorCodes.RequestInvalid);
            return request;
        }

        public static CadInspectRequestV1 LoadInspectRequest(string requestPath)
        {
            CadInspectRequestV1 request = Deserialize<CadInspectRequestV1>(requestPath);
            if (request == null || !string.Equals(request.Schema, CadDrawingSchemas.InspectRequest, StringComparison.Ordinal))
                throw new InvalidDataException(CadDrawingErrorCodes.SchemaUnknown);
            if (string.IsNullOrEmpty(request.RequestId) || string.IsNullOrEmpty(request.ResultJson))
                throw new InvalidDataException(CadDrawingErrorCodes.RequestInvalid);
            return request;
        }

        // ------------------------------------------------------------------
        // 校验（纯逻辑）
        // ------------------------------------------------------------------

        public static void ValidateDrawingRequest(CadDrawingRequestV1 request, string requestPath)
        {
            ValidateLayoutName(request.SourceLayout, allowModel: false);
            ValidateLayoutName(request.TargetLayout, allowModel: false);
            if (string.Equals(request.SourceLayout, request.TargetLayout, StringComparison.Ordinal))
                throw new InvalidDataException(CadDrawingErrorCodes.RequestInvalid);

            // 路径逃逸：请求 JSON 与结果 JSON 必须都在基础 DWG 所在 attempt 目录内。
            string attemptDirectory = Path.GetDirectoryName(Path.GetFullPath(request.BaseDwg));
            EnsureUnderDirectory(requestPath, attemptDirectory);
            EnsureUnderDirectory(request.ResultJson, attemptDirectory);

            if (!File.Exists(request.BaseDwg))
                throw new InvalidDataException(CadDrawingErrorCodes.BaseDwgMissing);
        }

        public static void ValidateLayoutName(string name, bool allowModel)
        {
            bool isModel = string.Equals(name, "Model", StringComparison.OrdinalIgnoreCase);
            if (string.IsNullOrWhiteSpace(name) || name.Length > 255 || (isModel && !allowModel))
                throw new InvalidDataException(CadDrawingErrorCodes.LayoutNameInvalid);
            if (name.IndexOfAny(InvalidNameCharacters) >= 0)
                throw new InvalidDataException(CadDrawingErrorCodes.LayoutNameInvalid);
            foreach (char value in name)
            {
                if (char.IsControl(value))
                    throw new InvalidDataException(CadDrawingErrorCodes.LayoutNameInvalid);
            }
        }

        public static void EnsureUnderDirectory(string candidatePath, string directoryPath)
        {
            if (string.IsNullOrEmpty(candidatePath) || string.IsNullOrEmpty(directoryPath))
                throw new InvalidDataException(CadDrawingErrorCodes.PathEscape);
            string fullCandidate = Path.GetFullPath(candidatePath);
            string fullDirectory = Path.GetFullPath(directoryPath);
            if (!fullDirectory.EndsWith(Path.DirectorySeparatorChar.ToString(), StringComparison.Ordinal))
                fullDirectory += Path.DirectorySeparatorChar;
            if (!fullCandidate.StartsWith(fullDirectory, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException(CadDrawingErrorCodes.PathEscape);
        }

        public static void ValidateSourceLayout(IEnumerable<string> availableLayouts, string sourceLayout)
        {
            foreach (string name in availableLayouts)
            {
                if (string.Equals(name, sourceLayout, StringComparison.OrdinalIgnoreCase))
                    return;
            }
            throw new InvalidDataException(CadDrawingErrorCodes.SourceLayoutMissing);
        }

        public static void ValidateTargetLayoutAvailable(IEnumerable<string> currentPaperLayouts, string targetLayout)
        {
            foreach (string name in currentPaperLayouts)
            {
                if (string.Equals(name, targetLayout, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException(CadDrawingErrorCodes.TargetLayoutConflict);
            }
        }

        public static void ValidateFinalPaperLayouts(IEnumerable<string> finalLayouts, string targetLayout)
        {
            var names = new List<string>(finalLayouts);
            var unique = new HashSet<string>(names, StringComparer.OrdinalIgnoreCase);
            if (names.Count != 1 || unique.Count != 1
                || !string.Equals(names[0], targetLayout, StringComparison.Ordinal))
                throw new InvalidDataException(CadDrawingErrorCodes.FinalLayoutSetInvalid);
        }

        public static void ValidateLayoutHandle(string handle)
        {
            if (string.IsNullOrEmpty(handle))
                throw new InvalidDataException(CadDrawingErrorCodes.HandleInvalid);
            foreach (char value in handle)
            {
                bool isHexDigit = (value >= '0' && value <= '9') || (value >= 'a' && value <= 'f') || (value >= 'A' && value <= 'F');
                if (!isHexDigit)
                    throw new InvalidDataException(CadDrawingErrorCodes.HandleInvalid);
            }
        }

        // ------------------------------------------------------------------
        // 序列化与原子写出
        // ------------------------------------------------------------------

        public static byte[] SerializeResult<T>(T result)
        {
            var serializer = new DataContractJsonSerializer(typeof(T));
            using (var stream = new MemoryStream())
            {
                serializer.WriteObject(stream, result);
                return stream.ToArray();
            }
        }

        public static void WriteResultAtomically(string resultPath, byte[] content)
        {
            // 同目录临时文件 + File.Delete/Move：读方要么见到旧结果、要么完整新结果。
            string temporary = Path.Combine(
                Path.GetDirectoryName(Path.GetFullPath(resultPath)),
                Path.GetFileName(resultPath) + ".tmp-" + Guid.NewGuid().ToString("N"));
            try
            {
                using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                {
                    stream.Write(content, 0, content.Length);
                    stream.Flush();
                }
                if (File.Exists(resultPath))
                    File.Delete(resultPath);
                File.Move(temporary, resultPath);
            }
            catch (Exception)
            {
                TryDelete(temporary);
                throw;
            }
        }

        // ------------------------------------------------------------------
        // 内部
        // ------------------------------------------------------------------

        private static T Deserialize<T>(string path) where T : class
        {
            try
            {
                using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
                {
                    var serializer = new DataContractJsonSerializer(typeof(T));
                    T value = serializer.ReadObject(stream) as T;
                    if (value == null || stream.Position != stream.Length || HasExtensionData(value))
                        throw new InvalidDataException(CadDrawingErrorCodes.RequestInvalid);
                    return value;
                }
            }
            catch (InvalidDataException)
            {
                throw;
            }
            catch (Exception exception) when (exception is IOException || exception is SerializationException || exception is ArgumentException)
            {
                throw new InvalidDataException(CadDrawingErrorCodes.RequestInvalid, exception);
            }
        }

        private static bool HasExtensionData(object value)
        {
            var extensible = value as IExtensibleDataObject;
            if (extensible == null || extensible.ExtensionData == null)
                return false;
            if (ExtensionDataMembersField == null)
                throw new InvalidDataException(CadDrawingErrorCodes.RequestInvalid);
            object members = ExtensionDataMembersField.GetValue(extensible.ExtensionData) as ICollection;
            return members != null && ((ICollection)members).Count > 0;
        }

        private static void TryDelete(string path)
        {
            try
            {
                if (File.Exists(path))
                    File.Delete(path);
            }
            catch (IOException)
            {
            }
        }

        [DataContract]
        private sealed class SchemaProbe
        {
            [DataMember(Name = "schema")]
            public string Schema { get; set; }
        }
    }
}
