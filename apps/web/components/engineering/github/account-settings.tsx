/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { AnchorButton } from "@makeplane/propel/components/anchor-button";
import { Banner } from "@makeplane/propel/components/banner";
import { Button } from "@makeplane/propel/components/button";
import { InputField } from "@makeplane/propel/components/input-field";
// plane imports
import { API_BASE_URL } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import type { TGitHubError } from "@plane/types";
// components
import { SettingsHeading } from "@/components/settings/heading";
// services
import { GitHubService } from "@/services/engineering/github.service";

const githubService = new GitHubService();

export const GITHUB_ACCOUNT_KEY = "GITHUB_ACCOUNT";

// What GitHub's sign-in sends people back with (?github=...), and the banner it shows
const RETURN_BANNERS = {
  connected: { variant: "info", key: "engineering.github.account.return.connected" },
  denied: { variant: "warning", key: "engineering.github.account.return.denied" },
  error: { variant: "danger", key: "engineering.github.account.return.error" },
} as const;

/** Profile settings: connect your own GitHub account, so reviews, merges and new pull requests are yours. */
export function GitHubAccountSettings() {
  // states
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  // hooks
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const returnBanner = RETURN_BANNERS[searchParams.get("github") as keyof typeof RETURN_BANNERS];
  const { data: account, mutate } = useSWR(GITHUB_ACCOUNT_KEY, () => githubService.getAccount());

  const handleConnect = async () => {
    setIsSaving(true);
    setError(null);
    try {
      await mutate(await githubService.connectAccount(token.trim()), { revalidate: false });
      setToken("");
    } catch (connectError) {
      const code = (connectError as TGitHubError | undefined)?.code ?? "github_error";
      setError(t(`engineering.github.errors.${code}`));
    } finally {
      setIsSaving(false);
    }
  };

  const handleDisconnect = async () => {
    await githubService.disconnectAccount();
    await mutate({ ...account, login: null } as typeof account, { revalidate: false });
  };

  if (!account) return null;

  return (
    <section className="flex w-full max-w-2xl flex-col gap-6">
      <SettingsHeading
        title={t("engineering.github.account.title")}
        description={t("engineering.github.account.description")}
      />
      {returnBanner && <Banner placement="inline" variant={returnBanner.variant} title={t(returnBanner.key)} />}
      {account.login ? (
        <div className="flex items-center gap-3">
          <span className="text-body-sm-regular" data-testid="github-account-login">
            {t("engineering.github.account.connected_as", { login: account.login })}
          </span>
          <Button
            variant="danger-outline"
            size="md"
            stretch="auto"
            label={t("engineering.github.settings.disconnect")}
            onClick={handleDisconnect}
          />
          {account.install_url && (
            <a
              href={account.install_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-body-xs-regular text-accent-primary hover:underline"
            >
              {t("engineering.github.account.install_more")}
            </a>
          )}
        </div>
      ) : account.oauth_available ? (
        <div>
          {/* A full-page visit: the API sends the person on to GitHub and back */}
          <AnchorButton
            href={`${API_BASE_URL}/api/github/oauth/start/`}
            variant="primary"
            size="md"
            label={t("engineering.github.account.connect_with_github")}
          />
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <InputField
            type="password"
            autoComplete="off"
            size="lg"
            orientation="vertical"
            label={t("engineering.github.account.token")}
            hint={t("engineering.github.account.token_hint")}
            error={error ?? undefined}
            value={token}
            onChange={(event) => setToken(event.target.value)}
          />
          <div>
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              loading={isSaving}
              disabled={!token.trim()}
              label={t("engineering.github.account.connect")}
              onClick={handleConnect}
            />
          </div>
        </div>
      )}
    </section>
  );
}
