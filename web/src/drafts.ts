import type { ChangeCommand, DraftAction, Workspace } from "./api/contracts";

function replacementKey(command: ChangeCommand): string | null {
  switch (command.type) {
    case "update_sheet_set":
      return command.type;
    case "update_subset_title":
      return `${command.type}:${command.subset_id}`;
    case "update_sheet_properties":
      return `${command.type}:${command.sheet_id}`;
    case "add_custom_property":
    case "delete_custom_property":
      return `custom_property:${command.property_type}:${command.name.toLocaleLowerCase()}`;
    case "delete_sheet":
      return `${command.type}:${command.sheet_id}`;
    case "delete_subset":
      return `${command.type}:${command.subset_id}`;
    default:
      return null;
  }
}

export function projectCommands(actions: DraftAction[], cursor: number): ChangeCommand[] {
  const projected: Array<ChangeCommand | null> = [];
  const previousByKey = new Map<string, number>();
  for (const action of actions.slice(0, cursor)) {
    for (const command of action.commands) {
      const key = replacementKey(command);
      if (key !== null) {
        const previous = previousByKey.get(key);
        if (previous !== undefined) projected[previous] = null;
        previousByKey.set(key, projected.length);
      }
      projected.push(command);
    }
  }
  return projected.filter((command): command is ChangeCommand => command !== null);
}

export function projectWorkspace(base: Workspace, actions: DraftAction[], cursor: number): Workspace {
  const projected: Workspace = JSON.parse(JSON.stringify(base));
  for (const command of projectCommands(actions, cursor)) {
    switch (command.type) {
      case "update_sheet_set":
        if (command.name !== undefined && command.name !== null) projected.sheet_set.name = command.name;
        if (command.custom_properties !== undefined && command.custom_properties !== null) {
          projected.sheet_set.custom_properties = { ...command.custom_properties };
        }
        break;
      case "update_subset_title": {
        const subset = projected.sheet_set.subsets.find((item) => item.id === command.subset_id);
        if (subset) subset.title = command.title;
        break;
      }
      case "update_sheet_properties": {
        const sheet = projected.sheet_set.subsets
          .flatMap((subset) => subset.sheets)
          .find((item) => item.id === command.sheet_id);
        if (sheet) sheet.custom_properties = { ...command.custom_properties };
        break;
      }
      case "add_custom_property":
        if (!projected.sheet_set.property_definitions.some(
          (item) => item.type === command.property_type && item.name.toLocaleLowerCase() === command.name.toLocaleLowerCase(),
        )) {
          projected.sheet_set.property_definitions.push({
            type: command.property_type,
            name: command.name,
            default_value: command.default_value,
          });
        }
        break;
      case "delete_custom_property":
        projected.sheet_set.property_definitions = projected.sheet_set.property_definitions.filter(
          (item) => !(item.type === command.property_type && item.name.toLocaleLowerCase() === command.name.toLocaleLowerCase()),
        );
        break;
    }
  }
  return projected;
}
