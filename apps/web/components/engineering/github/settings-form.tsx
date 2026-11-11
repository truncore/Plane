/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { Controller, useForm } from "react-hook-form";
import { Button } from "@makeplane/propel/components/button";
import { InputField } from "@makeplane/propel/components/input-field";
import { RadioGroupField, RadioGroupFieldOption } from "@makeplane/propel/components/radio-group-field";
// plane imports
import { Select } from "@plane/blocks/select";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { IState, TGitHubConnection, TGitHubConnectionPayload, TStateGroups, TWorkflowMode } from "@plane/types";
// hooks
import { useProjectState } from "@/hooks/store/use-project-state";

type TFormValues = Omit<TGitHubConnectionPayload, "repository_owner" | "repository_name"> & { repository: string };

type Props = {
  projectId: string;
  connection: TGitHubConnection | null;
  onSave: (data: Partial<TGitHubConnectionPayload>) => Promise<void>;
};

const REPOSITORY_PATTERN = /^[A-Za-z0-9-]+\/[A-Za-z0-9._-]+$/;

/** A random webhook secret made in the browser, to paste into GitHub before saving. */
const generateSecret = () =>
  Array.from(crypto.getRandomValues(new Uint8Array(24)), (byte) => byte.toString(16).padStart(2, "0")).join("");

const toFormValues = (connection: TGitHubConnection | null): TFormValues => ({
  repository: connection?.repository_full_name ?? "",
  token: "",
  webhook_secret: "",
  workflow_mode: connection?.workflow_mode ?? "trunk_based",
  base_branch: connection?.base_branch ?? "main",
  review_state_id: connection?.review_state_id ?? "",
  merged_state_id: connection?.merged_state_id ?? "",
  branch_age_limit_days: connection?.branch_age_limit_days ?? 2,
  large_pr_lines: connection?.large_pr_lines ?? 400,
});

export const GitHubSettingsForm = observer(function GitHubSettingsForm(props: Props) {
  const { projectId, connection, onSave } = props;
  // states
  const [isSecretVisible, setIsSecretVisible] = useState(false);
  // store hooks
  const { t } = useTranslation();
  const { getProjectStates } = useProjectState();
  // form
  const {
    control,
    handleSubmit,
    setValue,
    setError,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<TFormValues>({ values: toFormValues(connection) });
  // derived values
  const isTrunkBased = watch("workflow_mode") === "trunk_based";
  const statesInGroup = (group: TStateGroups) =>
    (getProjectStates(projectId) ?? []).filter((state) => state.group === group);

  const onSubmit = async ({ repository, ...values }: TFormValues) => {
    const [repository_owner, repository_name] = repository.split("/");
    try {
      await onSave({
        ...values,
        repository_owner,
        repository_name,
        // The server picks the default states on the first save
        review_state_id: values.review_state_id || undefined,
        merged_state_id: values.merged_state_id || undefined,
        branch_age_limit_days: Number(values.branch_age_limit_days),
        large_pr_lines: Number(values.large_pr_lines),
      });
      setIsSecretVisible(false);
      setToast({ type: "success", title: t("common.success"), message: t("engineering.github.settings.saved") });
    } catch (error) {
      const fieldErrors = (error ?? {}) as Record<string, string[] | string>;
      Object.entries(fieldErrors).forEach(([field, messages]) => {
        const name = (
          ["repository_owner", "repository_name"].includes(field) ? "repository" : field
        ) as keyof TFormValues;
        setError(name, { message: Array.isArray(messages) ? messages[0] : messages });
      });
      setToast({
        type: "error",
        title: t("common.error.label"),
        message: t("engineering.github.settings.save_failed"),
      });
    }
  };

  const renderStateSelect = (name: "review_state_id" | "merged_state_id", group: TStateGroups, label: string) => (
    <Controller
      control={control}
      name={name}
      render={({ field: { value, onChange } }) => {
        const states = statesInGroup(group);
        return (
          <div className="flex flex-col gap-1.5">
            <span className="text-body-xs-medium text-secondary">{label}</span>
            <Select<IState>
              getValues={() => states}
              value={states.find((state) => state.id === value) ?? null}
              onChange={(stateId) => onChange(stateId ?? "")}
              getOptionValue={(state) => state.id}
              getOptionLabel={(state) => state.name}
              showSearch={false}
              pinSelected={false}
            >
              <Select.Trigger<IState> variant="select-md" className="w-60" data-testid={`github-${name}`}>
                {(selected) => (
                  <span className="min-w-0 grow truncate text-left">
                    {selected[0]?.name ?? t("engineering.github.settings.default_state")}
                  </span>
                )}
              </Select.Trigger>
            </Select>
            {errors[name]?.message && (
              <span className="text-caption-sm-regular text-danger-primary">{errors[name]?.message}</span>
            )}
          </div>
        );
      }}
    />
  );

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-6">
      <Controller
        control={control}
        name="repository"
        rules={{
          required: t("engineering.github.settings.repository.required"),
          pattern: { value: REPOSITORY_PATTERN, message: t("engineering.github.settings.repository.invalid") },
        }}
        render={({ field }) => (
          <InputField
            {...field}
            size="lg"
            orientation="vertical"
            label={t("engineering.github.settings.repository.label")}
            placeholder="truncore/plane"
            hint={t("engineering.github.settings.repository.hint")}
            error={errors.repository?.message}
          />
        )}
      />
      <Controller
        control={control}
        name="token"
        rules={{ required: connection?.has_token ? false : t("engineering.github.settings.token.required") }}
        render={({ field }) => (
          <InputField
            {...field}
            type="password"
            autoComplete="off"
            size="lg"
            orientation="vertical"
            label={t("engineering.github.settings.token.label")}
            placeholder={connection?.has_token ? t("engineering.github.settings.saved_placeholder") : "github_pat_…"}
            hint={t("engineering.github.settings.token.hint")}
            error={errors.token?.message}
          />
        )}
      />
      <div className="flex items-end gap-2">
        <div className="grow">
          <Controller
            control={control}
            name="webhook_secret"
            rules={{
              required: connection?.has_webhook_secret
                ? false
                : t("engineering.github.settings.webhook_secret.required"),
            }}
            render={({ field }) => (
              <InputField
                {...field}
                type={isSecretVisible ? "text" : "password"}
                autoComplete="off"
                size="lg"
                orientation="vertical"
                label={t("engineering.github.settings.webhook_secret.label")}
                placeholder={connection?.has_webhook_secret ? t("engineering.github.settings.saved_placeholder") : ""}
                hint={t("engineering.github.settings.webhook_secret.hint")}
                error={errors.webhook_secret?.message}
              />
            )}
          />
        </div>
        <div className="mb-6">
          <Button
            variant="secondary"
            size="lg"
            stretch="auto"
            label={t("engineering.github.settings.webhook_secret.generate")}
            onClick={() => {
              setValue("webhook_secret", generateSecret(), { shouldDirty: true });
              setIsSecretVisible(true);
            }}
          />
        </div>
      </div>

      <Controller
        control={control}
        name="workflow_mode"
        render={({ field: { value, onChange } }) => (
          <RadioGroupField<TWorkflowMode>
            name="workflow_mode"
            label={t("engineering.github.settings.workflow_mode.label")}
            size="lg"
            density="comfortable"
            value={value}
            onValueChange={onChange}
          >
            <RadioGroupFieldOption
              value="trunk_based"
              label={t("engineering.github.settings.workflow_mode.trunk_based")}
              description={t("engineering.github.settings.workflow_mode.trunk_based_description")}
            />
            <RadioGroupFieldOption
              value="feature_branches"
              label={t("engineering.github.settings.workflow_mode.feature_branches")}
              description={t("engineering.github.settings.workflow_mode.feature_branches_description")}
            />
          </RadioGroupField>
        )}
      />
      <Controller
        control={control}
        name="base_branch"
        rules={{ required: t("engineering.github.settings.base_branch.required") }}
        render={({ field }) => (
          <InputField
            {...field}
            size="lg"
            orientation="vertical"
            label={t(
              isTrunkBased
                ? "engineering.github.settings.base_branch.trunk"
                : "engineering.github.settings.base_branch.label"
            )}
            placeholder="main"
            error={errors.base_branch?.message}
          />
        )}
      />
      {isTrunkBased && (
        <div className="flex flex-wrap gap-4">
          <Controller
            control={control}
            name="branch_age_limit_days"
            render={({ field }) => (
              <InputField
                {...field}
                value={String(field.value)}
                type="number"
                min={1}
                size="lg"
                orientation="vertical"
                label={t("engineering.github.settings.branch_age_limit_days")}
              />
            )}
          />
          <Controller
            control={control}
            name="large_pr_lines"
            render={({ field }) => (
              <InputField
                {...field}
                value={String(field.value)}
                type="number"
                min={1}
                size="lg"
                orientation="vertical"
                label={t("engineering.github.settings.large_pr_lines")}
              />
            )}
          />
        </div>
      )}

      <div className="flex flex-col gap-3">
        <span className="text-body-sm-medium">{t("engineering.github.settings.mapping.title")}</span>
        <div className="flex flex-wrap gap-4">
          {renderStateSelect("review_state_id", "started", t("engineering.github.settings.mapping.opened"))}
          {renderStateSelect("merged_state_id", "completed", t("engineering.github.settings.mapping.merged"))}
        </div>
        <p className="text-body-xs-regular text-tertiary">{t("engineering.github.settings.mapping.fixed_rules")}</p>
      </div>

      <div>
        <Button
          type="submit"
          variant="primary"
          size="lg"
          stretch="auto"
          loading={isSubmitting}
          label={t(connection ? "engineering.github.settings.save" : "engineering.github.settings.connect")}
        />
      </div>
    </form>
  );
});
