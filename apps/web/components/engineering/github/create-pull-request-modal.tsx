/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import useSWR, { mutate } from "swr";
import { Banner } from "@makeplane/propel/components/banner";
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { InputField } from "@makeplane/propel/components/input-field";
import { TextAreaField } from "@makeplane/propel/components/text-area-field";
// plane imports
import { Select } from "@plane/blocks/select";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { TGitHubBranch, TGitHubError } from "@plane/types";
import { calculateTimeAgo } from "@plane/utils";
// services
import { GitHubService } from "@/services/engineering/github.service";
// local imports
import { workItemGitHubKey } from "./work-item-github";

const githubService = new GitHubService();

const DAY_IN_MS = 24 * 60 * 60 * 1000;

type Props = {
  isOpen: boolean;
  onClose: () => void;
  onCreated: () => void;
  workspaceSlug: string;
  projectId: string;
  workItemId: string;
  /** e.g. PAY-12 */
  workItemKey: string;
  workItemName: string;
  requesterName: string;
};

export function CreatePullRequestModal(props: Props) {
  const { isOpen, onClose, onCreated, workspaceSlug, projectId, workItemId, workItemKey, workItemName, requesterName } =
    props;
  // states
  const [head, setHead] = useState("");
  const [base, setBase] = useState("");
  const [title, setTitle] = useState(`[${workItemKey}] ${workItemName}`);
  const [body, setBody] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  // hooks
  const { t } = useTranslation();
  // fetching
  // Loaded once per dialog: refreshing in the background would reset what the user picked
  const { data: branchData, error: branchError } = useSWR(
    isOpen ? `WORK_ITEM_BRANCHES_${workItemId}` : null,
    () => githubService.getBranches(workspaceSlug, projectId, workItemId),
    { revalidateOnFocus: false, revalidateIfStale: false }
  );
  const canPreview = !!head && !!base && head !== base;
  const { data: preview, error: previewError } = useSWR(
    isOpen && canPreview ? ["PULL_REQUEST_PREVIEW", workItemId, base, head] : null,
    () => githubService.previewPullRequest(workspaceSlug, projectId, workItemId, { base, head })
  );

  // Start from the suggested branch, the project's base branch and a description that links back
  useEffect(() => {
    if (!branchData) return;
    setBase(branchData.base_branch);
    setHead(branchData.branches.find((branch) => branch.suggested)?.name ?? "");
    const workItemUrl = `${window.location.origin}/${workspaceSlug}/browse/${workItemKey}/`;
    setBody(
      `${t("engineering.github.create_pr.body_work_item")}: [${workItemKey}](${workItemUrl})\n\n` +
        t("engineering.github.create_pr.body_opened_by", { name: requesterName })
    );
  }, [branchData, workspaceSlug, workItemKey, requesterName, t]);

  const errorMessage = (error: unknown) =>
    t(`engineering.github.errors.${(error as TGitHubError | undefined)?.code ?? "github_error"}`);

  const isStale = (branch: TGitHubBranch) =>
    branchData?.workflow_mode === "trunk_based" &&
    !!branch.last_commit_at &&
    Date.now() - new Date(branch.last_commit_at).getTime() > branchData.branch_age_limit_days * DAY_IN_MS;

  const blocked = !preview || preview.ahead_by === 0 || !!preview.existing_pull_request_url;

  const handleCreate = async () => {
    setIsCreating(true);
    setCreateError(null);
    try {
      const pullRequest = await githubService.createPullRequest(workspaceSlug, projectId, workItemId, {
        base,
        head,
        title,
        body,
      });
      await mutate(workItemGitHubKey(workItemId));
      onCreated();
      setToast({
        type: "success",
        title: t("common.success"),
        message: t("engineering.github.create_pr.created", { number: pullRequest.number }),
      });
      onClose();
    } catch (error) {
      setCreateError(errorMessage(error));
    } finally {
      setIsCreating(false);
    }
  };

  const branchSelect = branchData && (
    <div className="flex flex-col gap-1.5">
      <span className="text-body-xs-medium text-secondary">{t("engineering.github.create_pr.branch")}</span>
      <Select<TGitHubBranch>
        getValues={() => branchData.branches}
        value={branchData.branches.find((branch) => branch.name === head) ?? null}
        onChange={(name) => setHead(name ?? "")}
        getOptionValue={(branch) => branch.name}
        getOptionLabel={(branch) => {
          const age = branch.last_commit_at
            ? t("engineering.github.create_pr.last_commit", { time: calculateTimeAgo(branch.last_commit_at) })
            : "";
          const tags = [
            branch.suggested && t("engineering.github.create_pr.suggested"),
            isStale(branch) && t("engineering.github.create_pr.stale"),
          ].filter(Boolean);
          return [branch.name, age, ...tags].filter(Boolean).join(" · ");
        }}
        pinSelected={false}
      >
        <Select.Trigger<TGitHubBranch> variant="select-md" className="w-full" data-testid="create-pr-branch-select">
          {(selected) => (
            <span className="min-w-0 grow truncate text-left">
              {selected[0]?.name ?? t("engineering.github.create_pr.branch_placeholder")}
            </span>
          )}
        </Select.Trigger>
      </Select>
      {branchData.branches.length === 0 && (
        <span className="text-caption-sm-regular text-tertiary">{t("engineering.github.create_pr.no_branches")}</span>
      )}
    </div>
  );

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent size="lg">
        <DialogMain>
          <DialogHeader>
            <DialogHeading>
              <DialogTitle>{t("engineering.github.create_pr.title")}</DialogTitle>
            </DialogHeading>
          </DialogHeader>
          <DialogBody tabIndex={0}>
            <div className="flex flex-col gap-4" data-testid="create-pr-dialog">
              {branchError && <Banner placement="inline" variant="danger" title={errorMessage(branchError)} />}
              {branchSelect}
              <InputField
                size="lg"
                orientation="vertical"
                label={t("engineering.github.create_pr.base")}
                value={base}
                onChange={(event) => setBase(event.target.value)}
              />
              {preview && (
                <p className="text-body-xs-regular text-secondary" data-testid="create-pr-summary">
                  {t("engineering.github.create_pr.summary", {
                    commits: preview.ahead_by,
                    lines: preview.changed_lines,
                    files: preview.changed_files,
                  })}
                </p>
              )}
              {previewError && <Banner placement="inline" variant="danger" title={errorMessage(previewError)} />}
              {preview?.ahead_by === 0 && (
                <Banner placement="inline" variant="danger" title={t("engineering.github.errors.no_commits")} />
              )}
              {preview?.existing_pull_request_url && (
                <Banner
                  placement="inline"
                  variant="info"
                  title={t("engineering.github.errors.pr_exists")}
                  actions={
                    <a href={preview.existing_pull_request_url} target="_blank" rel="noopener noreferrer">
                      {t("engineering.github.create_pr.view_existing")}
                    </a>
                  }
                />
              )}
              {preview?.is_old_branch && branchData && (
                <Banner
                  placement="inline"
                  variant="warning"
                  title={t("engineering.github.create_pr.old_branch", {
                    days: preview.branch_age_days,
                    limit: branchData.branch_age_limit_days,
                  })}
                />
              )}
              {preview?.is_large && branchData && (
                <Banner
                  placement="inline"
                  variant="warning"
                  title={t("engineering.github.create_pr.large", {
                    lines: preview.changed_lines,
                    limit: branchData.large_pr_lines,
                  })}
                />
              )}
              <InputField
                size="lg"
                orientation="vertical"
                label={t("engineering.github.create_pr.title_label")}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
              />
              <TextAreaField
                size="lg"
                resize="vertical"
                label={t("engineering.github.create_pr.description")}
                value={body}
                onChange={(event) => setBody(event.target.value)}
              />
              {createError && <Banner placement="inline" variant="danger" title={createError} />}
            </div>
          </DialogBody>
        </DialogMain>
        <DialogActions>
          <Button variant="secondary" size="md" stretch="auto" label={t("cancel")} onClick={onClose} />
          <Button
            variant="primary"
            size="md"
            stretch="auto"
            label={t("engineering.github.create_pr.create")}
            loading={isCreating}
            disabled={blocked || !title.trim()}
            onClick={handleCreate}
          />
        </DialogActions>
      </DialogContent>
    </Dialog>
  );
}
