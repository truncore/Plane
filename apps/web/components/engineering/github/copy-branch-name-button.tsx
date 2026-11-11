/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { GitBranchOutline } from "@makeplane/propel/icons";
// plane imports
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import { copyTextToClipboard } from "@plane/utils";
// components
import { IssueDetailWidgetButton } from "@/components/issues/issue-detail-widgets/widget-button";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useProject } from "@/hooks/store/use-project";

/**
 * A branch name for a work item in the repository's convention, e.g. "feat/pay-12-reset-password":
 * lowercase, the work item ID, then up to five words of its name. Plane links branches by the ID.
 */
export const branchNameFor = (workItemKey: string, name: string) => {
  const words = name.toLowerCase().match(/[a-z0-9]+/g) ?? [];
  return [`feat/${workItemKey.toLowerCase()}`, ...words.slice(0, 5)].join("-");
};

type Props = {
  projectId: string;
  workItemId: string;
};

export const CopyBranchNameButton = observer(function CopyBranchNameButton(props: Props) {
  const { projectId, workItemId } = props;
  // store hooks
  const { t } = useTranslation();
  const { getProjectById } = useProject();
  const {
    issue: { getIssueById },
  } = useIssueDetail();
  // derived values
  const workItem = getIssueById(workItemId);
  const project = getProjectById(projectId);

  if (!workItem || !project) return null;

  const branchName = branchNameFor(`${project.identifier}-${workItem.sequence_id}`, workItem.name);

  return (
    <IssueDetailWidgetButton
      title={t("engineering.github.copy_branch.button")}
      icon={<GitBranchOutline className="h-3.5 w-3.5 flex-shrink-0" />}
      onClick={() =>
        copyTextToClipboard(branchName).then(() =>
          setToast({
            type: "success",
            title: t("engineering.github.copy_branch.copied"),
            message: branchName,
          })
        )
      }
    />
  );
});
