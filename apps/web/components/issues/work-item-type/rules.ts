/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback } from "react";
// plane imports
import { useTranslation } from "@plane/i18n";
import type { TIssue } from "@plane/types";
import { isEmptyHtmlString } from "@plane/utils";
// hooks
import { useWorkItemType } from "@/hooks/store/use-work-item-type";

/** A description with only empty paragraphs is empty; images count as content. */
export const isDescriptionEmpty = (descriptionHtml: string | undefined | null) =>
  isEmptyHtmlString(descriptionHtml ?? "", ["img", "image-component"]);

/** The description a new User Story starts with. */
export const useStoryTemplate = () => {
  const { t } = useTranslation();
  return (
    `<p>${t("work_item_types.story_template.statement")}</p>` +
    `<h3>${t("work_item_types.story_template.acceptance_criteria")}</h3>` +
    `<ul data-type="taskList"><li data-type="taskItem" data-checked="false"><p></p></li></ul>`
  );
};

/**
 * The User Story and Task rules the UI follows; the API enforces the same ones.
 * - Story points go on User Stories. A Task only shows points it already has, so they can be removed.
 * - A Task's parent is a User Story; a User Story has no parent and holds the tasks.
 */
export const useWorkItemTypeRules = () => {
  const { getWorkItemTypeKey } = useWorkItemType();
  const storyTemplate = useStoryTemplate();

  const isStory = useCallback(
    (typeId: string | null | undefined) => getWorkItemTypeKey(typeId) === "user_story",
    [getWorkItemTypeKey]
  );

  const showsStoryPoints = useCallback(
    (workItem: Pick<TIssue, "type_id" | "estimate_point">) => isStory(workItem.type_id) || !!workItem.estimate_point,
    [isStory]
  );

  /** Translation key of the reason a work item can't change to `typeId`, if any. */
  const getTypeChangeError = useCallback(
    (workItem: TIssue, typeId: string) => {
      if (isStory(typeId) && workItem.parent_id) return "work_item_types.rules.story_with_parent";
      if (!isStory(typeId) && isStory(workItem.type_id) && workItem.sub_issues_count)
        return "work_item_types.rules.story_with_tasks";
      return undefined;
    },
    [isStory]
  );

  /** The update for a type change: a Task drops its points, a new User Story gets the template. */
  const getTypeChangeData = useCallback(
    (workItem: TIssue, typeId: string): Partial<TIssue> => {
      if (!isStory(typeId)) return { type_id: typeId, ...(!!workItem.estimate_point && { estimate_point: null }) };
      return {
        type_id: typeId,
        ...(isDescriptionEmpty(workItem.description_html) && { description_html: storyTemplate }),
      };
    },
    [isStory, storyTemplate]
  );

  return { isStory, showsStoryPoints, getTypeChangeError, getTypeChangeData, storyTemplate };
};
