# 文档索引

本目录保存长期有效的事实、规范和可复用知识；有时效性的路线图、计划、待办和备忘请查阅 [`.planning/README.md`](../.planning/README.md)。

## 当前有效文档

- [Builder 退场与标准驱动创建提案（RFC-INT-003，accepted）](integration/rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md)：确认 Builder 直接退场，后续新建图纸集能力归入 DST Manager；治理架构与实现尚待后续文档和计划收口。
- [双产品与共享平台治理（ARCH-INT-002）](integration/architecture/ARCH-INT-002-dst-builder-manager-platform-governance.md)
- [DST Builder 历史入口](dst-builder/README.md)：RFC-INT-003 已接受产品直接退场，代码与文档归档尚待后续计划实施
- [DST Manager 文档入口](dst-manager/README.md)
- [Legacy Python 重构历史资料入口](legacy-refactor/README.md)
- [共享技术资料入口](shared/README.md)
- [跨项目整合入口](integration/README.md)

上述入口覆盖当前有效的长期文档；路线图、实施计划、待办和备忘请从开头的[执行资料索引](../.planning/README.md)进入。

## 规范与模板

文档类型、状态、编号和归属规则以[双产品与共享平台治理（ARCH-INT-002）](integration/architecture/ARCH-INT-002-dst-builder-manager-platform-governance.md)为唯一权威。已被取代的 [ARCH-INT-001](integration/architecture/ARCH-INT-001-documentation-organization.md)只保留历史背景。新增正式文档时从对应模板复制，并替换模板中的示例字段：

- [ADR 模板](_templates/adr.md)
- [Guide 模板](_templates/guide.md)
- [PRD 模板](_templates/prd.md)
- [Spec 模板](_templates/spec.md)
- [RFC 模板](_templates/rfc.md)

## 归档

当前暂无归档文档。首次产生需要长期追溯的归档时，再创建 `docs/archive/` 及其导航入口；不为尚无内容的归档目录提交空目录或 `.gitkeep`。
