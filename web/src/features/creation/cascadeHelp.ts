import {domIdToken} from "../../components/ui/domId";

export type CascadeHelpInput = {propertyId: string; sourcePropertyId: string; sourceName: string};
export type CascadeHelpGroup = {id: string; sourcePropertyId: string; sourceName: string; propertyIds: string[]};

export function groupCascadeHelp(
  instanceId: string,
  objectId: string,
  fields: readonly CascadeHelpInput[],
): CascadeHelpGroup[] {
  const groups = new Map<string, CascadeHelpGroup>();
  for (const field of fields) {
    let group = groups.get(field.sourcePropertyId);
    if (group === undefined) {
      group = {
        id: `cascade-help-${domIdToken(JSON.stringify([instanceId, objectId, field.sourcePropertyId]))}`,
        sourcePropertyId: field.sourcePropertyId,
        sourceName: field.sourceName,
        propertyIds: [],
      };
      groups.set(field.sourcePropertyId, group);
    }
    if (!group.propertyIds.includes(field.propertyId)) group.propertyIds.push(field.propertyId);
  }
  return [...groups.values()];
}
