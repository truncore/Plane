/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { TIssue } from "@plane/types";
// components
import { WorkItemTypeSelect } from "@/components/dropdowns/work-item-type/work-item-type-select";
// local imports
import { useWorkItemTypeRules } from "./rules";

type Props = {
  workItem: TIssue;
  disabled: boolean;
  onUpdate: (data: Partial<TIssue>) => void;
};

/** The work item type picker of the detail sidebar and peek panel, following the User Story and Task rules. */
export const WorkItemTypeProperty = observer(function WorkItemTypeProperty(props: Props) {
  const { workItem, disabled, onUpdate } = props;
  // store hooks
  const { t } = useTranslation();
  const { getTypeChangeError, getTypeChangeData } = useWorkItemTypeRules();

  const handleChange = (typeId: string) => {
    const error = getTypeChangeError(workItem, typeId);
    if (error) {
      setToast({ type: "error", title: t("common.error.label"), message: t(error) });
      return;
    }
    onUpdate(getTypeChangeData(workItem, typeId));
  };

  return (
    <WorkItemTypeSelect
      testId="work-item-type-select"
      value={workItem.type_id}
      onChange={handleChange}
      disabled={disabled}
      variant="select-ghost-md"
      tooltip
    />
  );
});
