import type { components } from "./schema";

export type PropertyType = "sheetset" | "sheet";
export type PropertyDefinition = components["schemas"]["PropertyDefinitionResponse"];
export type Sheet = components["schemas"]["SheetResponse"];
export type Subset = components["schemas"]["SubsetResponse"];
export type Diagnostic = components["schemas"]["DiagnosticResponse"];
type GeneratedDstValidation = components["schemas"]["DstValidationResponse"];
export type DstValidation = GeneratedDstValidation & {
  actions: components["schemas"]["RepairActionResponse"][];
  blocking_issues: Diagnostic[];
};
type GeneratedWorkspace = components["schemas"]["WorkspaceResponse"];
export type Workspace = Omit<GeneratedWorkspace, "dst_validation"> & {
  dst_validation: DstValidation;
};
export type JobFile = components["schemas"]["JobFileResponse"];
export type Job = components["schemas"]["JobResponse"];
export type Revision = components["schemas"]["RevisionResponse"];
export type RestorePreview = components["schemas"]["RestorePreviewResponse"];
export type RepairPreview = components["schemas"]["RepairPreviewResponse"];
export type DraftAction = components["schemas"]["DraftActionResponse"];
export type DraftEnvelope = components["schemas"]["DraftEnvelopeResponse"];

type GeneratedPreview = components["schemas"]["ChangePreviewResponse"];
export type Preview = GeneratedPreview;
export type CsvChange = components["schemas"]["PropertyCsvChangeResponse"];
export type CsvPreview = Omit<GeneratedPreview, "changes"> & { changes: CsvChange[] };
export type SemanticDiff = components["schemas"]["SemanticDiffResponse"];
export type ExecutionEstimate = components["schemas"]["ExecutionEstimateResponse"];
export type CardinalityFrontier = components["schemas"]["CardinalityFrontierResponse"];
export type SubsetOperation = components["schemas"]["SubsetOperationResponse"];
export type SourceBaseline = components["schemas"]["SourceBaselineResponse"];
export type DerivedSubset = components["schemas"]["DerivedSubsetResponse"];
export type CadGroup = components["schemas"]["CadGroupResponse"];

export type ChangeCommand = NonNullable<
  components["schemas"]["ChangePreviewRequest"]["commands"]
>[number];
export type Placement = "before" | "after";
export type LayoutSourceType = "existing_snapshot" | "template_layout";

type CommandOf<T extends ChangeCommand["type"]> = Extract<ChangeCommand, { type: T }>;

export const createCommand = {
  updateSheetSet(
    name: string,
    customProperties: Record<string, string>,
  ): CommandOf<"update_sheet_set"> {
    return { type: "update_sheet_set", name, custom_properties: customProperties };
  },
  updateSubsetTitle(subsetId: string, title: string): CommandOf<"update_subset_title"> {
    return { type: "update_subset_title", subset_id: subsetId, title };
  },
  updateSheetProperties(
    sheetId: string,
    customProperties: Record<string, string>,
  ): CommandOf<"update_sheet_properties"> {
    return { type: "update_sheet_properties", sheet_id: sheetId, custom_properties: customProperties };
  },
  deleteSheet(sheetId: string): CommandOf<"delete_sheet"> {
    return { type: "delete_sheet", sheet_id: sheetId };
  },
  deleteSubset(subsetId: string): CommandOf<"delete_subset"> {
    return {
      type: "delete_subset",
      subset_id: subsetId,
      confirm_delete_all_sheets: true,
      confirm_delete_main_dwg: true,
    };
  },
  addCustomProperty(
    propertyType: PropertyType,
    name: string,
    defaultValue: string,
  ): CommandOf<"add_custom_property"> {
    return { type: "add_custom_property", property_type: propertyType, name, default_value: defaultValue };
  },
  deleteCustomProperty(
    propertyType: PropertyType,
    name: string,
  ): CommandOf<"delete_custom_property"> {
    return { type: "delete_custom_property", property_type: propertyType, name };
  },
  insertSheet(input: Omit<CommandOf<"insert_sheet">, "type">): CommandOf<"insert_sheet"> {
    return { type: "insert_sheet", ...input };
  },
  insertSubset(input: Omit<CommandOf<"insert_subset">, "type">): CommandOf<"insert_subset"> {
    return { type: "insert_subset", ...input };
  },
};
