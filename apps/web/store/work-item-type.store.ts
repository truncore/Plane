/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { action, computed, makeObservable, observable, runInAction } from "mobx";
import { computedFn } from "mobx-utils";
// types
import type { TWorkItemType } from "@plane/types";
// services
import { WorkItemTypeService } from "@/services/issue";
// store
import type { CoreRootStore } from "./root.store";

export interface IWorkItemTypeStore {
  // observables
  workItemTypeMap: Record<string, TWorkItemType>;
  workspaceTypeIds: Record<string, string[]>;
  // computed
  currentWorkItemTypes: TWorkItemType[];
  defaultWorkItemTypeId: string | null;
  // computed actions
  getWorkItemTypeById: (typeId: string | null | undefined) => TWorkItemType | undefined;
  // fetch actions
  fetchWorkItemTypes: (workspaceSlug: string) => Promise<TWorkItemType[]>;
}

export class WorkItemTypeStore implements IWorkItemTypeStore {
  // observables
  workItemTypeMap: Record<string, TWorkItemType> = {};
  workspaceTypeIds: Record<string, string[]> = {};
  // root store
  rootStore;
  // services
  workItemTypeService;

  constructor(_rootStore: CoreRootStore) {
    makeObservable(this, {
      workItemTypeMap: observable,
      workspaceTypeIds: observable,
      currentWorkItemTypes: computed,
      defaultWorkItemTypeId: computed,
      fetchWorkItemTypes: action,
    });

    this.rootStore = _rootStore;
    this.workItemTypeService = new WorkItemTypeService();
  }

  /**
   * Returns the work item types of the current workspace
   */
  get currentWorkItemTypes() {
    const workspaceSlug = this.rootStore.router.workspaceSlug;
    if (!workspaceSlug) return [];
    const typeIds = this.workspaceTypeIds[workspaceSlug] ?? [];
    return typeIds.map((typeId) => this.workItemTypeMap[typeId]).filter((type) => !!type);
  }

  /**
   * Returns the id of the current workspace's default work item type
   */
  get defaultWorkItemTypeId() {
    return this.currentWorkItemTypes.find((type) => type.is_default)?.id ?? null;
  }

  getWorkItemTypeById = computedFn((typeId: string | null | undefined) =>
    typeId ? this.workItemTypeMap[typeId] : undefined
  );

  fetchWorkItemTypes = async (workspaceSlug: string) => {
    const workItemTypes = await this.workItemTypeService.getWorkspaceWorkItemTypes(workspaceSlug);
    runInAction(() => {
      workItemTypes.forEach((type) => {
        this.workItemTypeMap[type.id] = type;
      });
      this.workspaceTypeIds[workspaceSlug] = workItemTypes.map((type) => type.id);
    });
    return workItemTypes;
  };
}
