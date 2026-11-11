/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

export type TWorkItemTypeKey = "user_story" | "task";

export type TWorkItemType = {
  id: string;
  name: string;
  key: TWorkItemTypeKey;
  is_default: boolean;
};

/** How many of a User Story's tasks are done. */
export type TStoryProgress = {
  total: number;
  completed: number;
};
