import { api } from "@/controllers/API/api";
import { getBaseUrl } from "@/customization/utils/urls";

const authzUrl = (path: string) => `${getBaseUrl()}authz${path}`;

export type RbacStatus = {
  authz_enabled: boolean;
  audit_enabled: boolean;
  superuser_bypass: boolean;
  auto_login: boolean;
  is_superuser: boolean;
  production_ready: boolean;
  warnings: string[];
};

export type RbacUser = {
  id: string;
  username: string;
  is_active: boolean;
  is_superuser: boolean;
  create_at?: string;
  updated_at?: string;
};

export type UsersPage = {
  total_count: number;
  users: RbacUser[];
};

export type RbacRole = {
  id: string;
  name: string;
  description?: string | null;
  is_system: boolean;
  permissions: string[];
  parent_role_id?: string | null;
  workspace_id?: string | null;
  created_at: string;
  updated_at: string;
  created_by?: string | null;
};

export type RoleAssignment = {
  id: string;
  user_id: string;
  role_id: string;
  domain_type: string;
  domain_id?: string | null;
  assigned_at: string;
  assigned_by?: string | null;
};

export type Team = {
  id: string;
  team_name: string;
  adom_name: string;
  description?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type TeamMember = {
  id: string;
  team_id: string;
  user_id: string;
  source: string;
  created_at: string;
};

export type TeamRoleAssignment = {
  id: number;
  team_id: string;
  role_id: string;
  domain_type: string;
  domain_id?: string | null;
  assigned_by?: string | null;
};

export type ResourceShare = {
  id: string;
  resource_type: string;
  resource_id: string;
  scope: "private" | "team" | "user" | "public";
  target_id?: string | null;
  permission_level: "read" | "write" | "execute" | "admin";
  created_by?: string | null;
  created_at: string;
};

export type AuditEntry = {
  id: string;
  user_id?: string | null;
  action: string;
  resource_type?: string | null;
  resource_id?: string | null;
  result: "allow" | "deny" | "owner_override";
  details?: Record<string, unknown> | null;
  timestamp: string;
};

export type AuditPage = {
  items: AuditEntry[];
  total: number;
  page: number;
  size: number;
  pages: number;
};

export type IdentitySummary = {
  user_id: string;
  username: string;
  is_active: boolean;
  is_superuser: boolean;
  assignments: Array<
    RoleAssignment & {
      role_name: string;
    }
  >;
  teams: Array<{
    id: string;
    team_name: string;
    adom_name: string;
    source: string;
  }>;
  effective_permissions: string[];
  permission_catalog: string[];
};

export type IdentitySummaryScope = {
  domain_type: string;
  domain_id?: string | null;
};

export async function getRbacStatus(): Promise<RbacStatus> {
  const response = await api.get<RbacStatus>(authzUrl("/me/status"));
  return response.data;
}

export async function getIdentitySummary(
  userId?: string,
  scope?: IdentitySummaryScope,
): Promise<IdentitySummary> {
  const response = await api.get<IdentitySummary>(authzUrl("/me/summary"), {
    params: {
      user_id: userId || undefined,
      domain_type: scope?.domain_type,
      domain_id: scope?.domain_id || undefined,
    },
  });
  return response.data;
}

export async function getUsers(
  skip = 0,
  limit = 200,
  search?: string,
): Promise<UsersPage> {
  const response = await api.get<UsersPage>(`${getBaseUrl()}users/`, {
    params: { skip, limit, search: search || undefined },
  });
  return response.data;
}

export async function getRoles(): Promise<RbacRole[]> {
  const response = await api.get<RbacRole[]>(authzUrl("/roles"), {
    params: { limit: 200, offset: 0 },
  });
  return response.data;
}

export async function createRole(payload: {
  name: string;
  description?: string | null;
  permissions: string[];
  parent_role_id?: string | null;
}): Promise<RbacRole> {
  const response = await api.post<RbacRole>(authzUrl("/roles"), payload);
  return response.data;
}

export async function updateRole(
  roleId: string,
  payload: {
    name?: string;
    description?: string | null;
    permissions?: string[];
    parent_role_id?: string | null;
  },
): Promise<RbacRole> {
  const response = await api.patch<RbacRole>(
    authzUrl(`/roles/${roleId}`),
    payload,
  );
  return response.data;
}

export async function deleteRole(roleId: string): Promise<void> {
  await api.delete(authzUrl(`/roles/${roleId}`));
}

export async function getRoleAssignments(
  userId: string,
  scope?: IdentitySummaryScope,
): Promise<RoleAssignment[]> {
  const response = await api.get<RoleAssignment[]>(
    authzUrl("/role-assignments"),
    {
      params: {
        user_id: userId,
        domain_type: scope?.domain_type,
        domain_id: scope?.domain_id || undefined,
        limit: 200,
        offset: 0,
      },
    },
  );
  return response.data;
}

export async function createRoleAssignment(payload: {
  user_id: string;
  role_id: string;
  domain_type: string;
  domain_id?: string | null;
}): Promise<RoleAssignment> {
  const response = await api.post<RoleAssignment>(
    authzUrl("/role-assignments"),
    payload,
  );
  return response.data;
}

export async function deleteRoleAssignment(
  assignmentId: string,
): Promise<void> {
  await api.delete(authzUrl(`/role-assignments/${assignmentId}`));
}

export async function getTeams(search?: string): Promise<Team[]> {
  const response = await api.get<Team[]>(authzUrl("/teams"), {
    params: { search: search || undefined, limit: 200, offset: 0 },
  });
  return response.data;
}

export async function createTeam(payload: {
  team_name: string;
  adom_name: string;
  description?: string | null;
  is_active?: boolean;
}): Promise<Team> {
  const response = await api.post<Team>(authzUrl("/teams"), payload);
  return response.data;
}

export async function updateTeam(
  teamId: string,
  payload: Partial<
    Pick<Team, "team_name" | "adom_name" | "description" | "is_active">
  >,
): Promise<Team> {
  const response = await api.patch<Team>(authzUrl(`/teams/${teamId}`), payload);
  return response.data;
}

export async function deleteTeam(teamId: string): Promise<void> {
  await api.delete(authzUrl(`/teams/${teamId}`));
}

export async function getTeamMembers(teamId: string): Promise<TeamMember[]> {
  const response = await api.get<TeamMember[]>(
    authzUrl(`/teams/${teamId}/members`),
    { params: { limit: 200, offset: 0 } },
  );
  return response.data;
}

export async function addTeamMember(
  teamId: string,
  userId: string,
): Promise<TeamMember> {
  const response = await api.post<TeamMember>(
    authzUrl(`/teams/${teamId}/members`),
    { user_id: userId, source: "manual" },
  );
  return response.data;
}

export async function removeTeamMember(
  teamId: string,
  userId: string,
): Promise<void> {
  await api.delete(authzUrl(`/teams/${teamId}/members/${userId}`));
}

export async function getTeamRoles(
  teamId: string,
): Promise<TeamRoleAssignment[]> {
  const response = await api.get<TeamRoleAssignment[]>(
    authzUrl(`/teams/${teamId}/roles`),
  );
  return response.data;
}

export async function addTeamRole(
  teamId: string,
  payload: {
    role_id: string;
    domain_type: string;
    domain_id?: string | null;
  },
): Promise<TeamRoleAssignment> {
  const response = await api.post<TeamRoleAssignment>(
    authzUrl(`/teams/${teamId}/roles`),
    payload,
  );
  return response.data;
}

export async function removeTeamRole(
  teamId: string,
  ruleId: number,
): Promise<void> {
  await api.delete(authzUrl(`/teams/${teamId}/roles/${ruleId}`));
}

export async function getShares(): Promise<ResourceShare[]> {
  const response = await api.get<ResourceShare[]>(authzUrl("/shares"), {
    params: { limit: 200, offset: 0 },
  });
  return response.data;
}

export async function createShare(payload: {
  resource_type: string;
  resource_id: string;
  scope: ResourceShare["scope"];
  target_id?: string | null;
  permission_level: ResourceShare["permission_level"];
}): Promise<ResourceShare> {
  const response = await api.post<ResourceShare>(authzUrl("/shares"), payload);
  return response.data;
}

export async function updateShare(
  shareId: string,
  permissionLevel: ResourceShare["permission_level"],
): Promise<ResourceShare> {
  const response = await api.patch<ResourceShare>(
    authzUrl(`/shares/${shareId}`),
    { permission_level: permissionLevel },
  );
  return response.data;
}

export async function deleteShare(shareId: string): Promise<void> {
  await api.delete(authzUrl(`/shares/${shareId}`));
}

export async function getAuditPage(params: {
  page?: number;
  size?: number;
  user_id?: string;
  resource_type?: string;
  resource_id?: string;
  action?: string;
  result?: string;
  since?: string;
  until?: string;
  domain_type?: string;
  domain_id?: string;
}): Promise<AuditPage> {
  const response = await api.get<AuditPage>(authzUrl("/audit"), { params });
  return response.data;
}
