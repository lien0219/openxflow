export type FlowPersistenceNode = {
  type?: string;
  data?: {
    node?: {
      template?: Record<string, unknown>;
    };
  };
};

export type FlowPersistenceData = {
  nodes?: FlowPersistenceNode[];
  [key: string]: unknown;
};

export function isModelRefreshBody(value: unknown): boolean;
export function modelRefreshFlowId(value: unknown): string | undefined;
export function isModelRefreshBarrierSatisfied(
  completedModelRefreshes: number,
  expectedModelRefreshes: number,
): boolean;
export function modelRefreshNodeCount(data: FlowPersistenceData): number;
