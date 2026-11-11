/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import useSWR, { mutate } from "swr";
import { Badge } from "@makeplane/propel/components/badge";
import type { BadgeProps } from "@makeplane/propel/components/badge";
import { Banner } from "@makeplane/propel/components/banner";
import { Button } from "@makeplane/propel/components/button";
import { InputField } from "@makeplane/propel/components/input-field";
import { TextAreaField } from "@makeplane/propel/components/text-area-field";
// plane imports
import { Select } from "@plane/blocks/select";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { TGitHubError, TMergeMethod, TReviewEvent, TReviewVerdict } from "@plane/types";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// services
import { GitHubService } from "@/services/engineering/github.service";

const githubService = new GitHubService();

const MERGE_METHODS: TMergeMethod[] = ["merge", "squash", "rebase"];
const KNOWN_MERGEABLE_STATES = new Set(["clean", "unstable", "blocked", "behind", "dirty", "draft", "has_hooks"]);
const VERDICT_BADGES: Record<TReviewVerdict, BadgeProps["variant"]> = {
  APPROVED: "success",
  CHANGES_REQUESTED: "danger",
  COMMENTED: "neutral",
  DISMISSED: "neutral",
  PENDING: "warning",
};

type Props = {
  workspaceSlug: string;
  projectId: string;
  workItemId: string;
  pullRequestId: string;
  /** Key of the work item's pull request list, refreshed after an action */
  listKey: string;
};

/** Reviews, checks and mergeability of one pull request, with review and merge actions run as the person. */
export function PullRequestDetails(props: Props) {
  const { workspaceSlug, projectId, workItemId, pullRequestId, listKey } = props;
  // states
  const [comment, setComment] = useState("");
  const [reviewers, setReviewers] = useState("");
  const [mergeMethod, setMergeMethod] = useState<TMergeMethod>("squash");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  // hooks
  const { t } = useTranslation();
  const {
    issue: { fetchIssue },
  } = useIssueDetail();
  const detailsKey = `PULL_REQUEST_DETAILS_${pullRequestId}`;
  const { data: details, error } = useSWR(detailsKey, () =>
    githubService.getPullRequestDetails(workspaceSlug, projectId, workItemId, pullRequestId)
  );

  const errorMessage = (actionError: unknown) =>
    t(`engineering.github.errors.${(actionError as TGitHubError | undefined)?.code ?? "github_error"}`);

  /** Run an action on GitHub, then refresh this pull request, the list and the work item's state. */
  const runAction = async (name: string, action: () => Promise<void>, successMessage: string) => {
    setBusyAction(name);
    try {
      await action();
      await Promise.all([mutate(detailsKey), mutate(listKey), fetchIssue(workspaceSlug, projectId, workItemId)]);
      setToast({ type: "success", title: t("common.success"), message: successMessage });
    } catch (actionError) {
      setToast({ type: "error", title: t("common.error.label"), message: errorMessage(actionError) });
    } finally {
      setBusyAction(null);
    }
  };

  const review = (event: TReviewEvent) =>
    runAction(
      event,
      async () => {
        await githubService.reviewPullRequest(workspaceSlug, projectId, workItemId, pullRequestId, {
          event,
          body: comment,
        });
        setComment("");
      },
      t("engineering.github.pull_request.review_sent")
    );

  if (error) return <Banner placement="inline" variant="danger" title={errorMessage(error)} />;
  if (!details) return null;

  const mergeableState = KNOWN_MERGEABLE_STATES.has(details.mergeable_state) ? details.mergeable_state : "unknown";

  return (
    <div className="flex flex-col gap-3 rounded-md border border-subtle p-3" data-testid="pull-request-details">
      <div className="flex flex-wrap items-center gap-3 text-body-xs-regular">
        <span data-testid="pull-request-mergeable">
          {t(`engineering.github.pull_request.mergeable.${mergeableState}`)}
        </span>
        <a
          href={details.files_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-accent-primary hover:underline"
        >
          {t("engineering.github.pull_request.review_on_github")}
        </a>
      </div>

      <div className="flex flex-col gap-1">
        <span className="text-body-xs-medium">{t("engineering.github.pull_request.reviewers")}</span>
        {details.reviewers.length === 0 && (
          <span className="text-body-xs-regular text-tertiary">
            {t("engineering.github.pull_request.no_reviewers")}
          </span>
        )}
        {details.reviewers.map((reviewer) => (
          <div key={reviewer.login} className="flex items-center gap-2 text-body-xs-regular">
            <span>{reviewer.login}</span>
            <Badge
              size="sm"
              variant={VERDICT_BADGES[reviewer.state]}
              label={t(`engineering.github.pull_request.verdict.${reviewer.state}`)}
            />
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-1">
        <span className="text-body-xs-medium">{t("engineering.github.pull_request.checks")}</span>
        {details.checks.length === 0 && (
          <span className="text-body-xs-regular text-tertiary">{t("engineering.github.pull_request.no_checks")}</span>
        )}
        {details.checks.map((check) => (
          <a
            key={check.name}
            href={check.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 text-body-xs-regular hover:underline"
          >
            <span>{check.name}</span>
            <span className="text-tertiary">{check.conclusion ?? check.status}</span>
          </a>
        ))}
      </div>

      {details.acting_as ? (
        <div className="flex flex-col gap-3 border-t border-subtle pt-3">
          <span className="text-caption-sm-regular text-tertiary">
            {t("engineering.github.pull_request.acting_as", { login: details.acting_as })}
          </span>
          <div className="flex items-end gap-2">
            <div className="grow">
              <InputField
                size="lg"
                orientation="vertical"
                label={t("engineering.github.pull_request.request_review_label")}
                placeholder="octocat, hubot"
                value={reviewers}
                onChange={(event) => setReviewers(event.target.value)}
              />
            </div>
            <Button
              variant="secondary"
              size="lg"
              stretch="auto"
              label={t("engineering.github.pull_request.request_review")}
              loading={busyAction === "reviewers"}
              disabled={!reviewers.trim()}
              onClick={() =>
                runAction(
                  "reviewers",
                  async () => {
                    const logins = reviewers
                      .split(",")
                      .map((login) => login.trim())
                      .filter(Boolean);
                    await githubService.requestReviewers(workspaceSlug, projectId, workItemId, pullRequestId, logins);
                    setReviewers("");
                  },
                  t("engineering.github.pull_request.review_requested")
                )
              }
            />
          </div>
          <TextAreaField
            size="lg"
            resize="vertical"
            label={t("engineering.github.pull_request.comment")}
            value={comment}
            onChange={(event) => setComment(event.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              label={t("engineering.github.pull_request.approve")}
              loading={busyAction === "APPROVE"}
              disabled={!details.can_review}
              onClick={() => review("APPROVE")}
            />
            <Button
              variant="danger-outline"
              size="md"
              stretch="auto"
              label={t("engineering.github.pull_request.request_changes")}
              loading={busyAction === "REQUEST_CHANGES"}
              disabled={!details.can_review || !comment.trim()}
              onClick={() => review("REQUEST_CHANGES")}
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Select<TMergeMethod>
              getValues={() => MERGE_METHODS}
              value={mergeMethod}
              onChange={(method) => method && setMergeMethod(method as TMergeMethod)}
              getOptionValue={(method) => method}
              getOptionLabel={(method) => t(`engineering.github.pull_request.merge_method.${method}`)}
              showSearch={false}
              pinSelected={false}
            >
              <Select.Trigger<TMergeMethod> variant="select-md" className="w-48" data-testid="merge-method-select">
                {(selected) => (
                  <span className="min-w-0 grow truncate text-left">
                    {selected[0] && t(`engineering.github.pull_request.merge_method.${selected[0]}`)}
                  </span>
                )}
              </Select.Trigger>
            </Select>
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              label={t("engineering.github.pull_request.merge")}
              loading={busyAction === "merge"}
              disabled={!details.can_merge}
              onClick={() =>
                runAction(
                  "merge",
                  () =>
                    githubService.mergePullRequest(workspaceSlug, projectId, workItemId, pullRequestId, mergeMethod),
                  t("engineering.github.pull_request.merged")
                )
              }
            />
          </div>
        </div>
      ) : (
        <Banner
          placement="inline"
          variant="info"
          title={t("engineering.github.pull_request.connect_account")}
          actions={<a href="/settings/profile/github">{t("engineering.github.pull_request.connect_account_link")}</a>}
        />
      )}
    </div>
  );
}
