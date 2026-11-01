/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { BookmarkOutline } from "@makeplane/propel/icons";
// components
import { WorkItemTypeChangeMessage } from "@/components/issues/work-item-type";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// local components
import { IssueActivityBlockComponent } from "./";

type TIssueTypeActivity = { activityId: string; ends: "top" | "bottom" | undefined };

export const IssueTypeActivity = observer(function IssueTypeActivity(props: TIssueTypeActivity) {
  const { activityId, ends } = props;
  // hooks
  const {
    activity: { getActivityById },
  } = useIssueDetail();

  const activity = getActivityById(activityId);

  if (!activity) return <></>;
  return (
    <IssueActivityBlockComponent
      icon={<BookmarkOutline className="h-3.5 w-3.5 text-secondary" aria-hidden="true" />}
      activityId={activityId}
      ends={ends}
    >
      <WorkItemTypeChangeMessage typeId={activity.new_identifier} fallbackName={activity.new_value} />
    </IssueActivityBlockComponent>
  );
});
