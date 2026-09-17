// DstBuilder.AutoCAD 纯契约测试（SPEC-DB-001 §7 / PLAN-DB-001 Task 7）。
// 测试项目只链接纯 Contracts.cs，不加载任何 AutoCAD 程序集。覆盖：
// 未知 Schema 拒绝、路径逃逸拒绝、Model 保留布局名、源布局不存在、
// 目标布局冲突、最终布局集合校验与结果 JSON 原子写出。

using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using DstBuilder.AutoCAD;
using Xunit;

namespace DstBuilder.AutoCAD.Tests
{
    public class ContractValidationTests
    {
        private static string TempDir()
        {
            string directory = Path.Combine(Path.GetTempPath(), "dstb-tests-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(directory);
            return directory;
        }

        private static string WriteFile(string directory, string fileName, string content)
        {
            string path = Path.Combine(directory, fileName);
            File.WriteAllText(path, content, new UTF8Encoding(false));
            return path;
        }

        private static string ValidDrawingRequestJson(string attemptDir, string resultPath)
        {
            string baseDwg = WriteFile(attemptDir, "working.dwg", "fake dwg");
            return "{\"schema\":\"dst-builder.cad-drawing-request/v1\","
                + "\"request_id\":\"" + Guid.NewGuid().ToString("N") + "\","
                + "\"base_dwg\":\"" + JsonEscape(baseDwg) + "\","
                + "\"layout_asset\":\"assets/layout/layout-abc.dwg\","
                + "\"layout_asset_path\":\"" + JsonEscape(Path.Combine(attemptDir, "..", "assets", "layout-abc.dwg")) + "\","
                + "\"source_layout\":\"平面\","
                + "\"target_layout\":\"001 平面\","
                + "\"result_json\":\"" + JsonEscape(resultPath) + "\"}";
        }

        private static string JsonEscape(string value)
        {
            var builder = new StringBuilder();
            foreach (char character in value)
            {
                if (character == '\\') builder.Append("\\\\");
                else if (character == '"') builder.Append("\\\"");
                else builder.Append(character);
            }
            return builder.ToString();
        }

        // ------------------------------------------------------------------
        // 未知 Schema
        // ------------------------------------------------------------------

        [Fact]
        public void UnknownDrawingRequestSchemaIsRejected()
        {
            string dir = TempDir();
            try
            {
                string requestPath = WriteFile(dir, "request.json",
                    ValidDrawingRequestJson(dir, Path.Combine(dir, "result.json"))
                        .Replace("dst-builder.cad-drawing-request/v1", "dst-builder.cad-drawing-request/v2"));

                var error = Assert.Throws<InvalidDataException>(
                    () => CadDrawingContracts.LoadDrawingRequest(requestPath));
                Assert.Equal(CadDrawingErrorCodes.SchemaUnknown, error.Message);
            }
            finally { Directory.Delete(dir, true); }
        }

        [Fact]
        public void UnknownTopLevelFieldIsRejected()
        {
            string dir = TempDir();
            try
            {
                string json = ValidDrawingRequestJson(dir, Path.Combine(dir, "result.json"));
                string requestPath = WriteFile(dir, "request.json",
                    json.Substring(0, json.Length - 1) + ",\"injected\":1}");

                Assert.Throws<InvalidDataException>(
                    () => CadDrawingContracts.LoadDrawingRequest(requestPath));
            }
            finally { Directory.Delete(dir, true); }
        }

        [Fact]
        public void UnknownInspectRequestSchemaIsRejected()
        {
            string dir = TempDir();
            try
            {
                string requestPath = WriteFile(dir, "inspect.json",
                    "{\"schema\":\"other/v1\",\"request_id\":\"abc\",\"result_json\":\"r.json\"}");

                var error = Assert.Throws<InvalidDataException>(
                    () => CadDrawingContracts.LoadInspectRequest(requestPath));
                Assert.Equal(CadDrawingErrorCodes.SchemaUnknown, error.Message);
            }
            finally { Directory.Delete(dir, true); }
        }

        // ------------------------------------------------------------------
        // 路径逃逸
        // ------------------------------------------------------------------

        [Fact]
        public void ResultJsonOutsideAttemptDirectoryIsRejected()
        {
            string dir = TempDir();
            string elsewhere = TempDir();
            try
            {
                string requestPath = WriteFile(dir, "request.json",
                    ValidDrawingRequestJson(dir, Path.Combine(elsewhere, "result.json")));
                CadDrawingRequestV1 request = CadDrawingContracts.LoadDrawingRequest(requestPath);

                var error = Assert.Throws<InvalidDataException>(
                    () => CadDrawingContracts.ValidateDrawingRequest(request, requestPath));
                Assert.Equal(CadDrawingErrorCodes.PathEscape, error.Message);
            }
            finally { Directory.Delete(dir, true); Directory.Delete(elsewhere, true); }
        }

        [Fact]
        public void RequestOutsideAttemptDirectoryIsRejected()
        {
            string dir = TempDir();
            string elsewhere = TempDir();
            try
            {
                string requestPath = WriteFile(elsewhere, "request.json",
                    ValidDrawingRequestJson(dir, Path.Combine(dir, "result.json")));
                CadDrawingRequestV1 request = CadDrawingContracts.LoadDrawingRequest(requestPath);

                var error = Assert.Throws<InvalidDataException>(
                    () => CadDrawingContracts.ValidateDrawingRequest(request, requestPath));
                Assert.Equal(CadDrawingErrorCodes.PathEscape, error.Message);
            }
            finally { Directory.Delete(dir, true); Directory.Delete(elsewhere, true); }
        }

        [Fact]
        public void MissingBaseDwgIsRejected()
        {
            string dir = TempDir();
            try
            {
                string json = ValidDrawingRequestJson(dir, Path.Combine(dir, "result.json"));
                string baseDwg = Path.Combine(dir, "working.dwg");
                File.Delete(baseDwg);
                string requestPath = WriteFile(dir, "request.json", json);
                CadDrawingRequestV1 request = CadDrawingContracts.LoadDrawingRequest(requestPath);

                var error = Assert.Throws<InvalidDataException>(
                    () => CadDrawingContracts.ValidateDrawingRequest(request, requestPath));
                Assert.Equal(CadDrawingErrorCodes.BaseDwgMissing, error.Message);
            }
            finally { Directory.Delete(dir, true); }
        }

        [Fact]
        public void ValidRequestPassesValidation()
        {
            string dir = TempDir();
            try
            {
                string requestPath = WriteFile(dir, "request.json",
                    ValidDrawingRequestJson(dir, Path.Combine(dir, "result.json")));
                CadDrawingRequestV1 request = CadDrawingContracts.LoadDrawingRequest(requestPath);

                CadDrawingContracts.ValidateDrawingRequest(request, requestPath);
            }
            finally { Directory.Delete(dir, true); }
        }

        // ------------------------------------------------------------------
        // Model 保留布局名
        // ------------------------------------------------------------------

        [Theory]
        [InlineData("Model")]
        [InlineData("model")]
        [InlineData("MODEL")]
        public void TargetLayoutModelIsRejected(string target)
        {
            var request = new CadDrawingRequestV1
            {
                Schema = CadDrawingSchemas.DrawingRequest,
                RequestId = "abc",
                BaseDwg = @"C:\attempt\working.dwg",
                LayoutAsset = "assets/layout/layout-abc.dwg",
                LayoutAssetPath = @"C:\project\assets\layout\layout-abc.dwg",
                SourceLayout = "平面",
                TargetLayout = target,
                ResultJson = @"C:\attempt\result.json",
            };

            var error = Assert.Throws<InvalidDataException>(
                () => CadDrawingContracts.ValidateDrawingRequest(request, @"C:\attempt\request.json"));
            Assert.Equal(CadDrawingErrorCodes.LayoutNameInvalid, error.Message);
        }

        [Fact]
        public void SourceLayoutModelIsRejected()
        {
            var error = Assert.Throws<InvalidDataException>(
                () => CadDrawingContracts.ValidateLayoutName("Model", allowModel: false));
            Assert.Equal(CadDrawingErrorCodes.LayoutNameInvalid, error.Message);
        }

        [Fact]
        public void UnsafeLayoutNamesAreRejected()
        {
            foreach (string name in new[] { "", "  ", "平\n面", "a/b", "a\\b", "a:b", "a*b", "a?b", "a<b" })
            {
                Assert.Throws<InvalidDataException>(
                    () => CadDrawingContracts.ValidateLayoutName(name, allowModel: false));
            }
        }

        // ------------------------------------------------------------------
        // 源布局不存在
        // ------------------------------------------------------------------

        [Fact]
        public void SourceLayoutMissingIsRejected()
        {
            var error = Assert.Throws<InvalidDataException>(
                () => CadDrawingContracts.ValidateSourceLayout(new[] { "Layout1", "A1" }, "平面"));
            Assert.Equal(CadDrawingErrorCodes.SourceLayoutMissing, error.Message);
        }

        [Fact]
        public void SourceLayoutFoundPassesCaseInsensitively()
        {
            CadDrawingContracts.ValidateSourceLayout(new[] { "A1", "A2" }, "a1");
        }

        // ------------------------------------------------------------------
        // 目标布局冲突
        // ------------------------------------------------------------------

        [Fact]
        public void TargetLayoutConflictIsRejected()
        {
            var error = Assert.Throws<InvalidDataException>(
                () => CadDrawingContracts.ValidateTargetLayoutAvailable(new[] { "001 平面" }, "001 平面"));
            Assert.Equal(CadDrawingErrorCodes.TargetLayoutConflict, error.Message);
        }

        [Fact]
        public void TargetLayoutConflictIsCaseInsensitive()
        {
            var error = Assert.Throws<InvalidDataException>(
                () => CadDrawingContracts.ValidateTargetLayoutAvailable(new[] { "001 平面" }, "001 平面".ToUpper()));
            Assert.Equal(CadDrawingErrorCodes.TargetLayoutConflict, error.Message);
        }

        [Fact]
        public void FreeTargetLayoutPasses()
        {
            CadDrawingContracts.ValidateTargetLayoutAvailable(new[] { "Layout1" }, "001 平面");
        }

        // ------------------------------------------------------------------
        // 最终布局集合校验
        // ------------------------------------------------------------------

        [Fact]
        public void FinalLayoutSetMustBeExactlyTarget()
        {
            Assert.Throws<InvalidDataException>(
                () => CadDrawingContracts.ValidateFinalPaperLayouts(new[] { "Model", "001 平面" }, "001 平面"));
            Assert.Throws<InvalidDataException>(
                () => CadDrawingContracts.ValidateFinalPaperLayouts(new[] { "001 平面", "多余的" }, "001 平面"));
            Assert.Throws<InvalidDataException>(
                () => CadDrawingContracts.ValidateFinalPaperLayouts(new string[0], "001 平面"));
            CadDrawingContracts.ValidateFinalPaperLayouts(new[] { "001 平面" }, "001 平面");
        }

        [Fact]
        public void InvalidLayoutHandleIsRejected()
        {
            Assert.Throws<InvalidDataException>(() => CadDrawingContracts.ValidateLayoutHandle("GG12"));
            Assert.Throws<InvalidDataException>(() => CadDrawingContracts.ValidateLayoutHandle(""));
            CadDrawingContracts.ValidateLayoutHandle("2f");
        }

        // ------------------------------------------------------------------
        // 结果原子写出
        // ------------------------------------------------------------------

        [Fact]
        public void ResultIsWrittenAtomically()
        {
            string dir = TempDir();
            try
            {
                string resultPath = Path.Combine(dir, "result.json");
                byte[] content = Encoding.UTF8.GetBytes("{\"schema\":\"v1\"}");

                CadDrawingContracts.WriteResultAtomically(resultPath, content);

                Assert.Equal(content, File.ReadAllBytes(resultPath));
                // 不留临时文件。
                Assert.Empty(Directory.GetFiles(dir, "*.tmp-*"));
                // 覆盖已有结果同样是原子的。
                byte[] updated = Encoding.UTF8.GetBytes("{\"schema\":\"v1\",\"x\":2}");
                CadDrawingContracts.WriteResultAtomically(resultPath, updated);
                Assert.Equal(updated, File.ReadAllBytes(resultPath));
                Assert.Single(Directory.GetFiles(dir));
            }
            finally { Directory.Delete(dir, true); }
        }

        // ------------------------------------------------------------------
        // 结果序列化往返
        // ------------------------------------------------------------------

        [Fact]
        public void DrawingResultSerializesSnakeCaseFields()
        {
            var result = new CadDrawingResultV1
            {
                Schema = CadDrawingSchemas.DrawingResult,
                RequestId = "req-1",
                LayoutName = "001 平面",
                LayoutHandle = "2F",
                DatabaseVersion = "AC1027",
                Layouts = new List<string> { "001 平面" },
                Diagnostics = new List<CadDiagnostic> { },
            };

            string json = Encoding.UTF8.GetString(CadDrawingContracts.SerializeResult(result));

            // DataContractJsonSerializer 会把 "/" 转义为 "\/"，且成员按字母序输出。
            Assert.Contains("\"schema\":\"dst-builder.cad-drawing-result\\/v1\"", json);
            Assert.Contains("\"request_id\":\"req-1\"", json);
            Assert.Contains("\"layout_name\":\"001 平面\"", json);
            Assert.Contains("\"layout_handle\":\"2F\"", json);
            Assert.Contains("\"database_version\":\"AC1027\"", json);
            Assert.Contains("\"layouts\":", json);
        }

        [Fact]
        public void InspectResultSerializesLayouts()
        {
            var result = new CadInspectResultV1
            {
                Schema = CadDrawingSchemas.InspectResult,
                RequestId = "req-2",
                Layouts = new List<string> { "A1", "A2" },
            };

            string json = Encoding.UTF8.GetString(CadDrawingContracts.SerializeResult(result));

            Assert.Contains("\"schema\":\"dst-builder.cad-inspect-result\\/v1\"", json);
            Assert.Contains("\"layouts\":[\"A1\",\"A2\"]", json);
        }

        [Fact]
        public void DrawingRequestRoundTripsThroughPayload()
        {
            var request = new CadDrawingRequestV1
            {
                Schema = CadDrawingSchemas.DrawingRequest,
                RequestId = "req-3",
                BaseDwg = @"C:\attempt\working.dwg",
                LayoutAsset = "assets/layout/layout-abc.dwg",
                LayoutAssetPath = @"C:\project\assets\layout\layout-abc.dwg",
                SourceLayout = "平面",
                TargetLayout = "001 平面",
                ResultJson = @"C:\attempt\result.json",
            };

            string json = Encoding.UTF8.GetString(CadDrawingContracts.SerializeResult(request));
            string path = TempDir();
            try
            {
                string requestPath = WriteFile(path, "request.json", json);
                CadDrawingRequestV1 parsed = CadDrawingContracts.LoadDrawingRequest(requestPath);

                Assert.Equal(request.SourceLayout, parsed.SourceLayout);
                Assert.Equal(request.TargetLayout, parsed.TargetLayout);
                Assert.Equal(request.RequestId, parsed.RequestId);
            }
            finally { Directory.Delete(path, true); }
        }
    }
}
