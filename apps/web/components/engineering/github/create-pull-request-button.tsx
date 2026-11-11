/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { GitPullRequestOutline } from "@makeplane/propel/icons";
// plane imports
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
// components
import { IssueDetailWidgetButton } from "@/components/issues/issue-detail-widgets/widget-button";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useProject } from "@/hooks/store/use-project";
import { useUser, useUserPermissions } from "@/hooks/store/user";
// local imports
import { CreatePullRequestModal } from "./create-pull-request-modal";

type Props = {
  workspaceSlug: string;
  projectId: string;
  workItemId: string;
  disabled: boolean;
};

/** "Create PR" in a work item's action buttons, for people who can edit the project's work items. */
export const CreatePullRequestButton = observer(function CreatePullRequestButton(props: Props) {
  const { workspaceSlug, projectId, workItemId, disabled } = props;
  // states
  const [isModalOpen, setIsModalOpen] = useState(false);
  // store hooks
  const { t } = useTranslation();
  const { allowPermissions } = useUserPermissions();
  const { getProjectById } = useProject();
  const { data: currentUser } = useUser();
  const {
    issue: { getIssueById, fetchIssue },
  } = useIssueDetail();
  // derived values
  const workItem = getIssueById(workItemId);
  const project = getProjectById(projectId);
  const canEdit = allowPermissions(
    [EUserPermissions.ADMIN, EUserPermissions.MEMBER],
    EUserPermissionsLevel.PROJECT,
    workspaceSlug,
    projectId
  );

  if (!workItem || !project || !canEdit || disabled) return null;

  return (
    <>
      <IssueDetailWidgetButton
        title={t("engineering.github.create_pr.button")}
        icon={<GitPullRequestOutline className="h-3.5 w-3.5 flex-shrink-0" />}
        onClick={() => setIsModalOpen(true)}
      />
      <CreatePullRequestModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onCreated={() => fetchIssue(workspaceSlug, projectId, workItemId)}
        workspaceSlug={workspaceSlug}
        projectId={projectId}
        workItemId={workItemId}
        workItemKey={`${project.identifier}-${workItem.sequence_id}`}
        workItemName={workItem.name}
        requesterName={currentUser?.display_name ?? ""}
      />
    </>
  );
});
