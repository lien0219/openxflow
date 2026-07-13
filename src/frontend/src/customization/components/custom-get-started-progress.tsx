import { GetStartedProgress } from "@/components/core/folderSidebarComponent/components/sideBarFolderButtons/components/get-started-progress";
import type { Users } from "@/types/api";

export function CustomGetStartedProgress({
  userData,
  isGithubStarred,
  handleDismissDialog,
}: {
  userData: Users;
  isGithubStarred: boolean;
  handleDismissDialog: () => void;
}) {
  return (
    <GetStartedProgress
      userData={userData}
      isGithubStarred={isGithubStarred}
      handleDismissDialog={handleDismissDialog}
    />
  );
}

export default CustomGetStartedProgress;
