/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import useSWR from "swr";
import { Badge } from "@makeplane/propel/components/badge";
import type { BadgeProps } from "@makeplane/propel/components/badge";
import { GitCommitOutline, GitMergeOutline, GitPullRequestOutline } from "@makeplane/propel/icons";
// plane imports
import { useTranslation } from "@plane/i18n";
import type { TPullRequestState } from "@plane/types";
// services
import { GitHubService } from "@/services/engineering/github.service";
// local imports
import { PullRequestDetails } from "./pull-request-details";

const githubService = new GitHubService();

export const workItemGitHubKey = (workItemId: string) => `WORK_ITEM_GITHUB_${workItemId}`;

const STATE_BADGES: Record<TPullRequestState, BadgeProps["variant"]> = {
  open: "success",
  draft: "neutral",
  merged: "purple",
  closed: "danger",
};

type Props = {
  workspaceSlug: string;
  projectId: string;
  workItemId: string;
};

/** The pull requests and trunk commits linked to a work item. Hidden when there are none. */
export function WorkItemGitHub(props: Props) {
  const { workspaceSlug, projectId, workItemId } = props;
  const { t } = useTranslation();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  // Webhooks update these on the server, so check again every so often
  const { data } = useSWR(
    workItemGitHubKey(workItemId),
    () => githubService.getWorkItemGitHub(workspaceSlug, projectId, workItemId),
    { refreshInterval: 30_000 }
  );

  if (!data || (!data.pull_requests.length && !data.commits.length)) return null;

  return (
    <section className="flex flex-col gap-2 py-2" data-testid="work-item-github">
      <h3 className="text-body-sm-medium">{t("engineering.github.work_item.title")}</h3>
      <ul className="flex flex-col gap-1.5">
        {data.pull_requests.map((pullRequest) => (
          <li key={pullRequest.id} className="flex flex-col gap-2">
            <div className="flex min-w-0 items-center gap-2 text-body-xs-regular">
              {pullRequest.state === "merged" ? (
                <GitMergeOutline className="size-4 flex-shrink-0 text-tertiary" />
              ) : (
                <GitPullRequestOutline className="size-4 flex-shrink-0 text-tertiary" />
              )}
              <a
                href={pullRequest.url}
                target="_blank"
                rel="noopener noreferrer"
                className="min-w-0 truncate hover:underline"
              >
                #{pullRequest.number} {pullRequest.title}
              </a>
              <Badge
                size="sm"
                variant={STATE_BADGES[pullRequest.state]}
                label={t(`engineering.github.work_item.pull_request_state.${pullRequest.state}`)}
              />
              <span className="flex-shrink-0 truncate text-tertiary">
                {pullRequest.head_branch} → {pullRequest.base_branch}
              </span>
              <button
                type="button"
                className="flex-shrink-0 text-accent-primary hover:underline"
                onClick={() => setExpandedId(expandedId === pullRequest.id ? null : pullRequest.id)}
              >
                {t(
                  expandedId === pullRequest.id
                    ? "engineering.github.pull_request.hide"
                    : "engineering.github.pull_request.show"
                )}
              </button>
            </div>
            {expandedId === pullRequest.id && (
              <PullRequestDetails
                workspaceSlug={workspaceSlug}
                projectId={projectId}
                workItemId={workItemId}
                pullRequestId={pullRequest.id}
                listKey={workItemGitHubKey(workItemId)}
              />
            )}
          </li>
        ))}
        {data.commits.map((commit) => (
          <li key={commit.id} className="flex min-w-0 items-center gap-2 text-body-xs-regular">
            <GitCommitOutline className="size-4 flex-shrink-0 text-tertiary" />
            <a
              href={commit.url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-mono flex-shrink-0 hover:underline"
            >
              {commit.sha.slice(0, 7)}
            </a>
            <span className="min-w-0 truncate">{commit.message.split("\n")[0]}</span>
            <span className="flex-shrink-0 text-tertiary">{commit.author_login || commit.author_name}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
