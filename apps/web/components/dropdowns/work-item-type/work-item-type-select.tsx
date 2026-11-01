/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import { Select } from "@plane/blocks/select";
import type { SelectTooltip, SelectVariant } from "@plane/blocks/select";
import { useTranslation } from "@plane/i18n";
import type { TWorkItemType } from "@plane/types";
// components
import { WorkItemTypeIcon, useWorkItemTypeLabel } from "@/components/issues/work-item-type";
// hooks
import { useWorkItemType } from "@/hooks/store/use-work-item-type";

type WorkItemTypeSelectProps = {
  /** value-agnostic e2e selector — forwarded to the trigger as data-testid */
  testId?: string;
  /** Current work item type id (`null` / `undefined` shows the default type). */
  value: string | null | undefined;
  /** Emits the next work item type id. */
  onChange: (value: string) => void;
  variant: SelectVariant;
  disabled?: boolean;
  className?: string;
  tooltip?: SelectTooltip;
  /** Tab order of the trigger, for forms that sequence focus explicitly (`ETabIndices`). */
  tabIndex?: number;
};

export const WorkItemTypeSelect = observer(function WorkItemTypeSelect(props: WorkItemTypeSelectProps) {
  const { value, onChange, variant, disabled = false, className, tooltip, testId, tabIndex } = props;
  // store hooks
  const { t } = useTranslation();
  const { currentWorkItemTypes, defaultWorkItemTypeId } = useWorkItemType();
  const getLabel = useWorkItemTypeLabel();
  // derived values
  const selectedId = value ?? defaultWorkItemTypeId;
  const selected = currentWorkItemTypes.find((type) => type.id === selectedId) ?? null;
  const placeholder = t("work_item_types.label_singular");

  return (
    <Select<TWorkItemType>
      getValues={() => currentWorkItemTypes}
      value={selected}
      onChange={(typeId) => {
        if (typeId) onChange(typeId);
      }}
      disabled={disabled}
      placeholder={placeholder}
      showSearch={false}
      pinSelected={false}
      getOptionValue={(type) => type.id}
      getOptionLabel={(type) => getLabel(type)}
      getOptionIcon={(type) => <WorkItemTypeIcon typeKey={type.key} className="size-4 flex-shrink-0" />}
    >
      <Select.Trigger<TWorkItemType>
        disabled={disabled}
        variant={variant}
        tabIndex={tabIndex}
        className={className}
        data-testid={testId}
        prependIcon={(types) => <WorkItemTypeIcon typeKey={types[0]?.key} />}
        label={(types) => getLabel(types[0], placeholder)}
        tooltip={tooltip}
      >
        {(types) => <span className="min-w-0 grow truncate text-left">{getLabel(types[0], placeholder)}</span>}
      </Select.Trigger>
    </Select>
  );
});
