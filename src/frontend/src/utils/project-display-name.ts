import type { FolderType, ProjectListType } from "@/pages/MainPage/entities";

type ProjectNameTranslator = (
  key: "project.ownedBy" | "assistant.title",
  options?: { name: string; owner: string },
) => string;

export const getProjectDisplayName = (
  project: Pick<FolderType, "id" | "name" | "owner_username" | "is_owner">,
  t: ProjectNameTranslator,
): string => {
  // Keep the legacy database name stable for lookup and deletion protection.
  const name =
    project.name === "Langflow Assistant" ? t("assistant.title") : project.name;
  if (project.is_owner !== false || !project.owner_username) {
    return name;
  }

  return t("project.ownedBy", {
    name,
    owner: project.owner_username,
  });
};

export const getDefaultProjectId = (
  projects: ProjectListType[],
  defaultProjectName: string,
): string | undefined => {
  return (
    projects.find(
      (project) => project.is_owner && project.name === defaultProjectName,
    ) ??
    projects.find((project) => project.is_owner) ??
    projects.find((project) => project.name === defaultProjectName) ??
    projects[0]
  )?.id;
};
