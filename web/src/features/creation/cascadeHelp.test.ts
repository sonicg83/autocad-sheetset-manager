import {describe, expect, it} from "vitest";
import {groupCascadeHelp} from "./cascadeHelp";

describe("groupCascadeHelp", () => {
  it("same_parent_one_shared_help", () => {
    expect(groupCascadeHelp("groups-1", "group-1", [
      {propertyId: "region", sourcePropertyId: "discipline", sourceName: "专业"},
      {propertyId: "subregion", sourcePropertyId: "discipline", sourceName: "专业"},
      {propertyId: "detail", sourcePropertyId: "region", sourceName: "区域"},
    ])).toEqual([
      {
        id: "cascade-help-%5B%22groups-1%22%2C%22group-1%22%2C%22discipline%22%5D",
        sourcePropertyId: "discipline",
        sourceName: "专业",
        propertyIds: ["region", "subregion"],
      },
      {
        id: "cascade-help-%5B%22groups-1%22%2C%22group-1%22%2C%22region%22%5D",
        sourcePropertyId: "region",
        sourceName: "区域",
        propertyIds: ["detail"],
      },
    ]);
  });

  it("different_parent_separate_help", () => {
    const groups = groupCascadeHelp("project-1", "sheetset", [
      {propertyId: "region", sourcePropertyId: "discipline", sourceName: "专业"},
      {propertyId: "route", sourcePropertyId: "network", sourceName: "管网类型"},
    ]);

    expect(groups).toHaveLength(2);
    expect(groups.map(group => group.sourcePropertyId)).toEqual(["discipline", "network"]);
    expect(groups[0]?.propertyIds).toEqual(["region"]);
    expect(groups[1]?.propertyIds).toEqual(["route"]);
  });

  it("different_group_separate_help", () => {
    const field = [{propertyId: "region", sourcePropertyId: "discipline", sourceName: "专业"}];
    const first = groupCascadeHelp("groups-1", "group-1", field)[0];
    const second = groupCascadeHelp("groups-1", "group-2", field)[0];
    const otherInstance = groupCascadeHelp("groups-2", "group-1", field)[0];

    expect(first?.id).not.toBe(second?.id);
    expect(first?.id).not.toBe(otherInstance?.id);
  });

  it("shared_help_ids_do_not_collide", () => {
    const tuples = [
      ["a:b", "c", "d"],
      ["a-b", "c", "d"],
      ["a", "b:c", "d"],
      ["a", "b", "c:d"],
      ["a--b", "c", "d"],
      ["a", "b--c", "d"],
      ["ab", "c", "d"],
      ["a", "bc", "d"],
      ["值 空格", "百分%比", "前--后"],
      ["值-空格", "百分比", "前--后"],
      ["表单", "对象", "中文%:--"],
      ["对象", "group-1", "parent"],
      ["对象", "group", "1-parent"],
    ] as const;
    const ids = tuples.map(([instanceId, objectId, sourcePropertyId]) =>
      groupCascadeHelp(instanceId, objectId, [
        {propertyId: "field", sourcePropertyId, sourceName: "上级"},
      ])[0]?.id,
    );

    expect(new Set(ids).size).toBe(tuples.length);
    expect(ids.every(id => id !== undefined && !/\s/u.test(id))).toBe(true);
  });
});
