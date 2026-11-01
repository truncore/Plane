/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback } from "react";
import { observer } from "mobx-react";
import { BookmarkFilled, CheckSquareOutline } from "@makeplane/propel/icons";
// plane imports
import { useTranslation } from "@plane/i18n";
import type { TWorkItemType, TWorkItemTypeKey } from "@plane/types";
import { cn } from "@plane/utils";
// hooks
import { useWorkItemType } from "@/hooks/store/use-work-item-type";

const WORK_ITEM_TYPE_LABELS = {
  user_story: "work_item_types.built_in.user_story",
  task: "work_item_types.built_in.task",
} as const;

/** Returns a resolver for the localized name of a built-in work item type. */
export const useWorkItemTypeLabel = () => {
  const { t } = useTranslation();
  return useCallback(
    (type: TWorkItemType | undefined, fallback = "") => (type ? t(WORK_ITEM_TYPE_LABELS[type.key]) : fallback),
    [t]
  );
};

type TWorkItemTypeIconProps = {
  typeKey: TWorkItemTypeKey | undefined;
  className?: string;
};

export function WorkItemTypeIcon(props: TWorkItemTypeIconProps) {
  const { typeKey, className = "size-3.5 flex-shrink-0" } = props;

  if (typeKey === "user_story") return <BookmarkFilled className={cn("text-accent-secondary", className)} />;
  return <CheckSquareOutline className={cn("text-tertiary", className)} />;
}

type TWorkItemTypeBadgeProps = {
  typeId: string | null | undefined;
};

/** Marks user stories in work item lists. Tasks are the default, so they carry no badge. */
export const WorkItemTypeBadge = observer(function WorkItemTypeBadge(props: TWorkItemTypeBadgeProps) {
  const { typeId } = props;
  // store hooks
  const { getWorkItemTypeById } = useWorkItemType();
  const getLabel = useWorkItemTypeLabel();
  // derived values
  const workItemType = getWorkItemTypeById(typeId);

  if (workItemType?.key !== "user_story") return null;

  return (
    <span
      className="inline-flex flex-shrink-0 items-center gap-1 rounded-sm bg-accent-primary/20 px-1 text-11 font-medium whitespace-nowrap text-accent-secondary"
      data-testid="work-item-type-badge"
    >
      <WorkItemTypeIcon typeKey={workItemType.key} className="size-3 flex-shrink-0" />
      {getLabel(workItemType)}
    </span>
  );
});

type TWorkItemTypeChangeProps = {
  typeId: string | null | undefined;
  fallbackName: string | null | undefined;
};

/** Activity text for a type change. Names a deleted or unknown type by the value stored on the activity. */
export const WorkItemTypeChangeMessage = observer(function WorkItemTypeChangeMessage(props: TWorkItemTypeChangeProps) {
  const { typeId, fallbackName } = props;
  // store hooks
  const { t } = useTranslation();
  const { getWorkItemTypeById } = useWorkItemType();
  const getLabel = useWorkItemTypeLabel();

  return (
    <>{t("work_item_types.activity.changed_to", { type: getLabel(getWorkItemTypeById(typeId), fallbackName ?? "") })}</>
  );
});
