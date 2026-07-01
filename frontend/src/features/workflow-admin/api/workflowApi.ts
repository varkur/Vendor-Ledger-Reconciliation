/**
 * Workflow Engine API client.
 */
import { apiClient } from '@shared/services/apiClient';

export interface WorkflowDefinition {
  id: string;
  code: string;
  name: string;
  description: string;
  entity_type: string;
  version: number;
  is_active: boolean;
  created_date: string;
}

export interface WorkflowStatus {
  id: string;
  workflow_definition_id: string;
  code: string;
  name: string;
  is_initial: boolean;
  is_terminal: boolean;
  sequence: number;
}

export interface WorkflowTransition {
  id: string;
  workflow_definition_id: string;
  from_status_id: string;
  to_status_id: string;
  action_code: string;
  guard_expression: string | null;
  requires_comment: boolean;
  auto_execute: boolean;
  priority: number;
}

export interface ApprovalMatrix {
  id: string;
  code: string;
  name: string;
  entity_type: string;
  priority: number;
  is_active: boolean;
  rules: { field: string; operator: string; value: string; data_type: string; logical_group: string }[];
  assignments: { level: number; assignment_type: string; user_id: string | null; role_id: string | null }[];
}

export const workflowApi = {
  // Definitions
  listDefinitions: async () => {
    const { data } = await apiClient.get<{ definitions: WorkflowDefinition[]; total: number }>('/workflow/definitions');
    return data;
  },
  createDefinition: async (req: { code: string; name: string; description: string; entity_type: string }) => {
    const { data } = await apiClient.post<WorkflowDefinition>('/workflow/definitions', req);
    return data;
  },
  getDefinition: async (id: string) => {
    const { data } = await apiClient.get<{ definition: WorkflowDefinition; statuses: WorkflowStatus[]; transitions: WorkflowTransition[] }>(`/workflow/definitions/${id}`);
    return data;
  },

  // Statuses
  createStatus: async (definitionId: string, req: { code: string; name: string; is_initial: boolean; is_terminal: boolean; sequence: number }) => {
    const { data } = await apiClient.post<WorkflowStatus>(`/workflow/definitions/${definitionId}/statuses`, req);
    return data;
  },

  // Transitions
  createTransition: async (definitionId: string, req: { from_status_id: string; to_status_id: string; action_code: string; requires_comment: boolean }) => {
    const { data } = await apiClient.post<WorkflowTransition>(`/workflow/definitions/${definitionId}/transitions`, req);
    return data;
  },
  deleteTransition: async (transitionId: string) => {
    await apiClient.delete(`/workflow/transitions/${transitionId}`);
  },

  // Approval Matrix
  listMatrices: async () => {
    const { data } = await apiClient.get<ApprovalMatrix[]>('/workflow/approval-matrices');
    return data;
  },
  createMatrix: async (req: any) => {
    const { data } = await apiClient.post<ApprovalMatrix>('/workflow/approval-matrices', req);
    return data;
  },
  updateMatrix: async (matrixId: string, req: any) => {
    const { data } = await apiClient.put<ApprovalMatrix>(`/workflow/approval-matrices/${matrixId}`, req);
    return data;
  },
};
