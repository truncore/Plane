/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import useSWR from "swr";
import { Banner } from "@makeplane/propel/components/banner";
import { Button } from "@makeplane/propel/components/button";
// plane imports
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { TGitHubConnectionPayload, TGitHubError } from "@plane/types";
import { copyTextToClipboard } from "@plane/utils";
// components
import { SettingsHeading } from "@/components/settings/heading";
// hooks
import { useProjectState } from "@/hooks/store/use-project-state";
// services
import { GitHubService } from "@/services/engineering/github.service";
// local imports
import { GitHubSettingsForm } from "./settings-form";

const githubService = new GitHubService();

export const githubSettingsKey = (projectId: string) => `GITHUB_SETTINGS_${projectId}`;

type TTestResult = { type: "success" | "error"; message: string };

type Props = {
  workspaceSlug: string;
  projectId: string;
};

export const GitHubSettings = observer(function GitHubSettings(props: Props) {
  const { workspaceSlug, projectId } = props;
  // states
  const [testResult, setTestResult] = useState<TTestResult | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  // store hooks
  const { t } = useTranslation();
  const { fetchProjectStates } = useProjectState();
  // fetching
  const { data: settings, mutate } = useSWR(githubSettingsKey(projectId), () =>
    githubService.getSettings(workspaceSlug, projectId)
  );
  const connection = settings?.connection ?? null;

  const handleSave = async (data: Partial<TGitHubConnectionPayload>) => {
    const saved = await githubService.saveSettings(workspaceSlug, projectId, data);
    await mutate(saved, { revalidate: false });
    // The first save may add the "In Review" state
    await fetchProjectStates(workspaceSlug, projectId);
    setTestResult(null);
  };

  const handleTest = async () => {
    setIsTesting(true);
    try {
      const result = await githubService.testConnection(workspaceSlug, projectId);
      setTestResult({
        type: "success",
        message: t("engineering.github.test.success", {
          repository: result.repository,
          branch: connection?.base_branch ?? result.default_branch,
        }),
      });
    } catch (error) {
      const code = (error as TGitHubError | undefined)?.code ?? "github_error";
      setTestResult({ type: "error", message: t(`engineering.github.errors.${code}`) });
    } finally {
      setIsTesting(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      await githubService.disconnect(workspaceSlug, projectId);
      await mutate();
      setTestResult(null);
    } catch {
      setToast({ type: "error", title: t("common.error.label"), message: t("common.something_went_wrong") });
    }
  };

  if (!settings) return null;

  return (
    <section className="flex w-full max-w-2xl flex-col gap-8">
      <SettingsHeading
        title={t("engineering.github.settings.title")}
        description={t("engineering.github.settings.description")}
      />

      {connection && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-body-sm-regular">
              {t("engineering.github.settings.connected_to", { repository: connection.repository_full_name })}
            </span>
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              loading={isTesting}
              label={t("engineering.github.test.button")}
              onClick={handleTest}
            />
            <Button
              variant="danger-outline"
              size="md"
              stretch="auto"
              label={t("engineering.github.settings.disconnect")}
              onClick={handleDisconnect}
            />
          </div>
          {testResult && (
            <div data-testid="github-test-result">
              <Banner
                placement="inline"
                variant={testResult.type === "success" ? "info" : "danger"}
                title={testResult.message}
              />
            </div>
          )}
        </div>
      )}

      <GitHubSettingsForm projectId={projectId} connection={connection} onSave={handleSave} />

      <div className="flex flex-col gap-2 rounded-md border border-subtle p-4">
        <span className="text-body-sm-medium">{t("engineering.github.webhook.title")}</span>
        <div className="flex flex-wrap items-center gap-2">
          <code className="rounded-sm bg-layer-2 px-2 py-1 text-body-xs-regular">{settings.webhook_url}</code>
          <Button
            variant="ghost"
            size="sm"
            stretch="auto"
            label={t("engineering.github.webhook.copy")}
            onClick={() =>
              copyTextToClipboard(settings.webhook_url).then(() =>
                setToast({ type: "success", title: t("engineering.github.webhook.copied") })
              )
            }
          />
        </div>
        <ol className="list-decimal pl-5 text-body-xs-regular text-secondary">
          <li>{t("engineering.github.webhook.step_open")}</li>
          <li>{t("engineering.github.webhook.step_fill")}</li>
          <li>{t("engineering.github.webhook.step_events")}</li>
        </ol>
        <p className="text-body-xs-regular text-tertiary">{t("engineering.github.webhook.public_url_note")}</p>
      </div>
    </section>
  );
});
