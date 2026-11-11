/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { LinearProgress } from "@makeplane/propel/components/linear-progress";
// plane imports
import { useTranslation } from "@plane/i18n";
// hooks
import { useWorkItemType } from "@/hooks/store/use-work-item-type";

type Props = {
  projectId: string;
  storyId: string;
};

/** "3 of 5 tasks done" with a small bar, for a User Story that has tasks. */
export const StoryProgress = observer(function StoryProgress(props: Props) {
  const { projectId, storyId } = props;
  // store hooks
  const { t } = useTranslation();
  const { getStoryProgress } = useWorkItemType();
  // derived values
  const progress = getStoryProgress(projectId, storyId);

  if (!progress?.total) return null;

  const label = t("work_item_types.progress.tasks_done", { completed: progress.completed, total: progress.total });

  return (
    <div
      className="flex h-5 flex-shrink-0 items-center gap-1.5 rounded-sm border-[0.5px] border-strong px-2"
      data-testid="story-progress"
    >
      <div className="w-8">
        <LinearProgress
          value={(progress.completed / progress.total) * 100}
          size="sm"
          variant="success"
          showValue={false}
          aria-label={label}
        />
      </div>
      <span className="text-caption-sm-regular whitespace-nowrap">{label}</span>
    </div>
  );
});
